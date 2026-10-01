"""Synthetic-only checks: no model downloads, outcome files, or provider calls."""
import copy
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from experiments.jlens_causal_report import protocol as p


@pytest.fixture(autouse=True)
def isolated_token_artifact_path(monkeypatch):
    monkeypatch.setattr(p, "TOKEN_BINDINGS_PATH",
                        "data/jlens_causal_report/_synthetic_test_inputs/token_bindings.json")


class TokenizerFixture:
    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {"tokenize": True, "add_generation_prompt": True,
                          "padding": False, "truncation": False}
        return [128000] + list(p.canonical(messages).encode()) + [128006]


def _token_artifact():
    return {**p.token_binding_inventory(TokenizerFixture()),
            "tokenizer_files": {name: {"sha256": "1" * 64, "git_blob_sha1": "2" * 40,
                                       "size_bytes": 100, "storage": "git_blob"} for name in p.TOKENIZER_FILES}}


def _write_token_artifact(root, artifact=None):
    path = root / p.TOKEN_BINDINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(p.canonical(_token_artifact() if artifact is None else artifact) + "\n")
    return path


def test_exact_inventory_and_directional_denominators():
    rows = p.inventory()
    assert len(rows) == len({row["id"] for row in rows}) == 76
    cases = [case for row in rows for case in row["cases"]]
    assert len(cases) == len({case["id"] for case in cases}) == 152
    for split, pairs in (("discovery", 32), ("qualification", 32), ("positive", 12)):
        selected = [row for row in rows if row["split"] == split]
        trials = p.directional_trials(rows, split=split)
        assert len(selected) == pairs
        assert len(trials) == len({trial["id"] for trial in trials}) == 2 * pairs
        assert all(trial["recipient_answer"] != trial["donor_answer"] for trial in trials)
        for row in selected:
            by_id = {case["id"]: case for case in row["cases"]}
            assert {d["recipient_id"] for d in row["directions"]} == set(by_id)
            assert {d["donor_id"] for d in row["directions"]} == set(by_id)
            for direction in row["directions"]:
                assert direction["donor_answer"] == by_id[direction["donor_id"]]["expected_answer"]
                assert direction["recipient_answer"] == by_id[direction["recipient_id"]]["expected_answer"]
    with pytest.raises(ValueError):
        p.directional_trials(split="reports")


@pytest.mark.parametrize("split", ["discovery", "qualification"])
def test_full_factorial_counterbalance_within_each_family(split):
    rows = [row for row in p.inventory() if row["split"] == split]
    for family in {row["family"] for row in rows}:
        selected = [row for row in rows if row["family"] == family]
        cells = [tuple(row["counterbalance"][key] for key in ("role", "probe", "order", "code"))
                 for row in selected]
        assert sorted(cells) == list(itertools.product((0, 1), repeat=4))
        for code in ("A", "B"):
            assert sum(row["answer_codes"]["self"] == code for row in selected) == 8
        for row in selected:
            own, other = row["cases"]
            assert own["owner"] == "self" and other["owner"] == "other"
            assert own["assignment"][row["probe"]] == row["self_role"]
            assert other["assignment"][row["probe"]] != row["self_role"]
            assert set(own["assignment"].values()) == set(other["assignment"].values()) == set(row["roles"])
            assert all(own["assignment"][obj] != other["assignment"][obj] for obj in row["objects"])
            for case in row["cases"]:
                assert case["expected_answer"] == row["answer_codes"][case["owner"]]
                text = case["messages"][0]["content"]
                assert f"your inventory = {row['answer_codes']['self']}" in text
                assert f"other participant's inventory = {row['answer_codes']['other']}" in text
                assert f"{row['self_role']} denotes you" in text
                assert f"{row['probe']}." in text
                for obj, role in case["assignment"].items():
                    assert f"{role} owns {obj}" in text
                entries = next(line for line in text.splitlines() if " owns " in line)
                roles = row["roles"][::(-1 if row["counterbalance"]["order"] else 1)]
                assert entries.index(roles[0]) < entries.index(roles[1])


def test_discovery_qualification_disjoint_and_prompts_neutral():
    rows = p.inventory()
    vocab = {}
    for split in ("discovery", "qualification"):
        chosen = [row for row in rows if row["split"] == split]
        vocab[split] = {word for row in chosen for word in row["roles"] + row["objects"]}
    assert vocab["discovery"].isdisjoint(vocab["qualification"])
    for row in rows:
        for case in row["cases"]:
            text = p.canonical(case["messages"])
            assert case["messages_sha256"] == hashlib.sha256(text.encode()).hexdigest()
            for prohibited in ("experien", "conscious", "feel", "sentien", "subjective", "perhaps"):
                assert prohibited not in text.lower()
    assert len({case["messages_sha256"] for row in rows for case in row["cases"]}) == 152


def test_bridge_answers_follow_both_record_links_and_fixed_code_map():
    rows = [row for row in p.inventory() if row["split"] == "positive"]
    assert len(rows) == 12
    for row in rows:
        for case in row["cases"]:
            assert case["expected_answer"] == row["answer_codes"][case["locker_color"]]
            text = case["messages"][0]["content"]
            for obj, holder in case["holders"].items():
                assert f"{holder} holds the {obj}" in text
            assert f"{case['locker_color']} = {case['expected_answer']}" in text
        assert row["cases"][0]["holders"] != row["cases"][1]["holders"]


def test_controller_api_budget_pins_and_phase_boundary():
    plan = p.build_plan()
    assert plan["budget"] == {
        "prior_usd": "69.130940", "new_cap_usd": "15", "total_usd": "200",
        "main_seconds": 7200, "cheap_seconds": 1800, "reserve_seconds": 600,
        "new_pro_calls": 0, "external_judge_calls": 0}
    assert (p.PRIOR_USD, p.NEW_CAP_USD, p.MAIN_SECONDS, p.CHEAP_SECONDS, p.RESERVE_SECONDS) == (
        "69.130940", "15", 7200, 1800, 600)
    assert plan["model"]["revision"] == p.pins.MODEL_REVISION
    assert plan["lens"]["sha256"] == p.pins.JLENS_FILE_SHA256
    assert plan["lens"]["role"] == "readout_only_not_candidate_selection"
    assert plan["lens"]["random_seeds"] == list(p.pins.TRANSPORT_RANDOM_SEEDS)
    assert plan["lens"]["comparators"] == ["identity", "jacobian"] + [f"random_j_{i}" for i in range(1, 6)]
    assert plan["inference"]["layers"] == [40, 50]
    assert plan["inference"]["max_new_tokens"] == 1
    assert plan["inference"]["decoding"] == "global_vocabulary_argmax_no_AB_restriction_or_renormalization"
    assert plan["inference"]["answer_tokenization"]["strings"] == ["A", "B", " A", " B"]
    assert plan["inference"]["answer_tokenization"]["each_must_be_singleton"]
    assert plan["inference"]["answer_tokenization"]["decoded_strip_must_equal_code"]
    assert plan["inference"]["conditional_AB_mass"].startswith("diagnostic_only")
    assert plan["candidate"]["rank"] == 1
    assert not any(plan["scope"][key] for key in (
        "experiential_reports", "paid_execution_authorized", "stage_b_frozen", "qwen_included"))
    assert plan["future_measurement_choice"]["report_items_in_this_plan"] == 0
    assert plan["future_measurement_choice"]["primary"].startswith("inclusive_")
    assert plan["future_measurement_choice"]["mandatory_secondary"].startswith("explicit_")
    assert "not_executed" in plan["interventions"]["later_layer_rescue"]
    assert plan["restoration_contract_deferred"]["restore_layer"] == 50
    assert "results" not in plan and not plan["input_hashes"]
    assert len(plan["interventions"]["random_seeds"]) == 5


def test_gates_are_directed_counts_and_delivery_is_not_operator_norm_ratio():
    gates = p.build_plan()["gates"]
    assert gates["qualification"]["denominator"] == 64
    assert gates["qualification"]["clean_correct_min"] == 58
    assert gates["qualification"]["target_donor_correct_min"] == 48
    assert gates["qualification"]["random_donor_correct_max_each_seed"] == 8
    assert gates["qualification"]["conditioning_on_clean_correct"] is False
    assert gates["delivery"]["joint_pass_fraction_min"] == .95
    assert gates["delivery"]["cosine_min"] == .95
    assert gates["delivery"]["relative_error_max"] == .25
    assert gates["delivery"]["actual_edit_over_clean_recipient_norm_max"] == .1
    assert gates["delivery"]["operator_norm_ratio_is_not_residual_norm_ratio"]
    assert gates["delivery"]["full_state_positive_exempt_from_residual_norm_cap"]
    assert gates["exact_noop"] == ["zero", "sham"]


def test_source_closure_and_repeated_build_are_deterministic():
    paths = p.source_paths()
    assert paths == sorted(set(paths))
    for required in (
        "experiments/jlens_causal_report/protocol.py", "experiments/jlens_causal_report/backend.py",
        "experiments/jlens_causal_report/operators.py", "experiments/jlens_causal_report/__init__.py",
        "experiments/exp2_sae/sae_jlens_protocol.py", "experiments/sae_assay_diagnostic/backend.py",
        "experiments/sae_assay_diagnostic/controller.py", "experiments/sae_assay_diagnostic/protocol.py",
        "experiments/sae_assay_exposure_lifecycle_a1/controller.py", "src/prompts.py",
        "tests/test_jlens_causal_protocol.py", p.PROTOCOL_DOC,
    ):
        assert required in paths
    assert all(not Path(path).is_absolute() and ".." not in Path(path).parts for path in paths)
    first = p.build_plan()
    assert p.canonical(first) == p.canonical(p.build_plan())
    assert set(first["source_hashes"]) == set(paths)
    assert all(p.sha(p.ROOT / name) == digest for name, digest in first["source_hashes"].items())


@pytest.fixture
def miniature_source(tmp_path, monkeypatch):
    source = tmp_path / "module.py"
    source.write_text("VALUE = 1\n")
    monkeypatch.setattr(p, "ROOT", tmp_path)
    monkeypatch.setattr(p, "source_paths", lambda: ["module.py"])
    plan = p.build_plan()
    path = tmp_path / "PLAN.json"
    path.write_text(p.canonical(plan) + "\n")
    return path, plan, source


def test_load_roundtrip_and_source_drift(miniature_source):
    path, plan, source = miniature_source
    assert p.load_plan(path) == plan
    source.write_text("VALUE = 2\n")
    with pytest.raises(ValueError, match="drift"):
        p.load_plan(path)


@pytest.mark.parametrize("mutation", ["inventory", "gate", "budget", "hash", "extra", "bool_count"])
def test_canonical_but_changed_plan_rejected(miniature_source, mutation):
    path, plan, _ = miniature_source
    if mutation == "inventory":
        plan["rows"][0]["cases"][0]["expected_answer"] = "Z"
    elif mutation == "gate":
        plan["gates"]["qualification"]["target_donor_correct_min"] = 47
    elif mutation == "budget":
        plan["budget"]["new_cap_usd"] = "16"
    elif mutation == "hash":
        plan["source_hashes"] = {}
    elif mutation == "bool_count":
        plan["candidate"]["rank"] = True
    else:
        plan["results"] = {"synthetic": 1}
    path.write_text(p.canonical(plan) + "\n")
    with pytest.raises(ValueError, match="drift"):
        p.load_plan(path)


def test_noncanonical_and_nonfinite_rejected(miniature_source):
    path, plan, _ = miniature_source
    path.write_text(json.dumps(plan, indent=2))
    with pytest.raises(ValueError, match="Noncanonical"):
        p.load_plan(path)
    with pytest.raises(ValueError):
        p.canonical({"bad": float("nan")})


@pytest.mark.parametrize("freeze", ["abc123", "A" * 40, "main", True])
def test_full_freeze_required(miniature_source, freeze):
    with pytest.raises(ValueError, match="full lowercase"):
        p.load_plan(miniature_source[0], freeze)


@pytest.mark.parametrize("drift", [None, "head", "blob", "plan"])
def test_freeze_binds_head_source_and_plan_without_git_writes(miniature_source, monkeypatch, drift):
    path, _, source = miniature_source
    artifact_path = _write_token_artifact(source.parent)
    plan = p.build_plan()
    path.write_text(p.canonical(plan) + "\n")
    freeze = "a" * 40

    def fake_git(command, **kwargs):
        assert kwargs["cwd"] == source.parent
        if command == ["git", "rev-parse", "HEAD"]:
            return ("b" * 40 if drift == "head" else freeze) + "\n"
        if command == ["git", "show", freeze + ":module.py"]:
            return b"tampered" if drift == "blob" else source.read_bytes()
        if command == ["git", "show", freeze + ":" + p.TOKEN_BINDINGS_PATH]:
            return artifact_path.read_bytes()
        assert command == ["git", "show", freeze + ":" + p.PLAN_PATH]
        return b"tampered" if drift == "plan" else path.read_bytes()

    monkeypatch.setattr(p.subprocess, "check_output", fake_git)
    if drift:
        with pytest.raises(ValueError, match="freeze"):
            p.load_plan(path, freeze)
    else:
        assert p.load_plan(path, freeze) == plan


@pytest.fixture
def synthetic_states(monkeypatch):
    monkeypatch.setattr(p, "MODEL_WIDTH", 4)
    states = {}
    for row in p.inventory():
        if row["split"] != "discovery":
            continue
        for case in row["cases"]:
            sign = 1 if case["owner"] == "self" else -1
            # Different layers must yield different independently fitted directions.
            states[case["id"]] = {40: [1 + sign * -2, 2, 3, 4],
                                  50: [1, 2 + sign * 3, 3, 4]}
    return states


def test_fp32_fit_orientation_center_and_artifact_hashes(synthetic_states):
    artifact = p.fit_candidates(synthetic_states)
    assert artifact == p.fit_candidates(copy.deepcopy(synthetic_states))
    assert artifact["layers"]["40"]["direction"] == [-1., 0., 0., 0.]
    assert artifact["layers"]["50"]["direction"] == [0., 1., 0., 0.]
    for layer in artifact["layers"].values():
        assert layer["center"] == [1., 2., 3., 4.]
        assert len(layer["discovery_state_sha256"]) == 64
        for field in ("direction", "center"):
            expected = hashlib.sha256(np.asarray(layer[field], dtype="<f4").tobytes()).hexdigest()
            assert layer[field + "_sha256"] == expected
        payload = {key: value for key, value in layer.items() if key != "sha256"}
        assert layer["sha256"] == hashlib.sha256(p.canonical(payload).encode()).hexdigest()
    payload = {key: value for key, value in artifact.items() if key != "sha256"}
    assert artifact["sha256"] == hashlib.sha256(p.canonical(payload).encode()).hexdigest()


@pytest.mark.parametrize("defect", ["extra", "missing", "layer", "width", "nan", "zero"])
def test_candidate_fit_rejects_wrong_or_degenerate_inputs(synthetic_states, defect):
    key = next(iter(synthetic_states))
    if defect == "extra":
        synthetic_states["qualification-forbidden"] = synthetic_states[key]
    elif defect == "missing":
        del synthetic_states[key]
    elif defect == "layer":
        synthetic_states[key][30] = synthetic_states[key].pop(40)
    elif defect == "width":
        synthetic_states[key][40] = [1, 2]
    elif defect == "nan":
        synthetic_states[key][40][0] = float("nan")
    else:
        for value in synthetic_states.values():
            value[40] = [1, 2, 3, 4]
    with pytest.raises(ValueError):
        p.fit_candidates(synthetic_states)


def test_fitting_uses_fp32_not_incoming_float64(synthetic_states):
    key = next(iter(synthetic_states))
    first = p.fit_candidates(synthetic_states)
    synthetic_states[key][40] = np.asarray(synthetic_states[key][40], dtype=np.float64)
    synthetic_states[key][40][2] += 1e-10
    assert p.fit_candidates(synthetic_states) == first


def test_protocol_direct_execution_imports_no_torch():
    # The parent-owned package initializer currently imports operators/torch.
    # Loading just this module proves that protocol and pin dependencies do not.
    command = (
        "import runpy, sys; "
        "sys.modules['torch'] = None; "
        f"m = runpy.run_path({str(Path(p.__file__))!r}); "
        "assert len(m['inventory']()) == 76"
    )
    subprocess.run([sys.executable, "-B", "-c", command], cwd=p.ROOT, check=True,
                   capture_output=True, text=True)


def test_token_binding_inventory_exact_messages_and_generation_boundary():
    bindings = p.token_binding_inventory(TokenizerFixture())
    assert set(bindings) == {"schema", "model_id", "revision", "cases"}
    assert bindings["model_id"] == p.pins.MODEL_ID and bindings["revision"] == p.pins.MODEL_REVISION
    assert len(bindings["cases"]) == 152
    for row in p.inventory():
        for case in row["cases"]:
            bound = bindings["cases"][case["id"]]
            assert bound["messages_sha256"] == case["messages_sha256"]
            assert bound["input_token_ids"] == [128000] + list(p.canonical(case["messages"]).encode()) + [128006]


@pytest.mark.parametrize("defect", ["case", "messages", "revision", "empty", "bool", "negative", "vocab", "nested"])
def test_token_bindings_reject_wrong_inventory_or_tokens(defect):
    artifact = _token_artifact()
    key = next(iter(artifact["cases"]))
    if defect == "case":
        del artifact["cases"][key]
    elif defect == "messages":
        artifact["cases"][key]["messages_sha256"] = "0" * 64
    elif defect == "revision":
        artifact["revision"] = "0" * 40
    else:
        bad = {"empty": [], "bool": [True], "negative": [-1], "vocab": [128256], "nested": [[1]]}
        artifact["cases"][key]["input_token_ids"] = bad[defect]
    with pytest.raises(ValueError):
        p.validate_token_bindings(artifact, require_files=True)


def test_draft_freeze_refused_without_download_or_git(miniature_source, monkeypatch):
    path, plan, _ = miniature_source
    assert plan["token_bindings"] is None and plan["scope"]["ready_to_freeze"] is False
    monkeypatch.setattr(p.subprocess, "check_output", lambda *a, **k: pytest.fail("No Git call for draft"))
    with pytest.raises(ValueError, match="without file-bound"):
        p.load_plan(path, "a" * 40)


def test_in_memory_bindings_remain_draft_and_file_artifact_promotes(miniature_source):
    path, _, source = miniature_source
    binding = p.token_binding_inventory(TokenizerFixture())
    draft = p.build_plan(token_bindings=binding)
    assert draft["token_bindings"] == binding
    assert not draft["scope"]["ready_to_freeze"] and draft["input_hashes"] == {}
    path.write_text(p.canonical(draft) + "\n")
    assert p.load_plan(path) == draft
    artifact = _token_artifact()
    artifact_path = _write_token_artifact(source.parent, artifact)
    production = p.build_plan()
    assert production["token_bindings"] == artifact and production["scope"]["ready_to_freeze"] is True
    assert production["input_hashes"] == {p.TOKEN_BINDINGS_PATH: p.sha(artifact_path)}
    assert p.build_plan(token_bindings=artifact) == production
    assert p.build_plan(token_bindings=artifact_path) == production


@pytest.mark.parametrize("defect", ["missing_file", "changed_file", "noncanonical", "no_file_hashes"])
def test_plan_rejects_token_artifact_drift(miniature_source, defect):
    path, _, source = miniature_source
    artifact = _token_artifact()
    artifact_path = _write_token_artifact(source.parent, artifact)
    plan = p.build_plan()
    path.write_text(p.canonical(plan) + "\n")
    if defect == "missing_file":
        artifact_path.unlink()
    elif defect == "changed_file":
        artifact["cases"][next(iter(artifact["cases"]))]["input_token_ids"].append(1)
        artifact_path.write_text(p.canonical(artifact) + "\n")
    elif defect == "noncanonical":
        artifact_path.write_text(json.dumps(artifact, indent=2))
    else:
        del artifact["tokenizer_files"]
        artifact_path.write_text(p.canonical(artifact) + "\n")
    with pytest.raises(ValueError):
        p.load_plan(path)


def test_frozen_input_blob_must_equal_artifact(miniature_source, monkeypatch):
    path, _, source = miniature_source
    _write_token_artifact(source.parent)
    path.write_text(p.canonical(p.build_plan()) + "\n")
    freeze = "a" * 40

    def fake_git(command, **kwargs):
        if command == ["git", "rev-parse", "HEAD"]:
            return freeze + "\n"
        if command == ["git", "show", freeze + ":module.py"]:
            return source.read_bytes()
        assert command == ["git", "show", freeze + ":" + p.TOKEN_BINDINGS_PATH]
        return b"wrong-input-blob"

    monkeypatch.setattr(p.subprocess, "check_output", fake_git)
    with pytest.raises(ValueError, match="differs from freeze"):
        p.load_plan(path, freeze)


@pytest.mark.parametrize("storage", ["git_blob", "lfs_dict", "lfs_object"])
def test_download_helper_only_requests_pinned_tokenizer_json(tmp_path, monkeypatch, storage):
    from types import SimpleNamespace
    import huggingface_hub
    import transformers

    files = {}
    for name in p.TOKENIZER_FILES:
        raw = ("synthetic " + name).encode()
        (tmp_path / name).write_bytes(raw)
        files[name] = raw
    siblings = [SimpleNamespace(rfilename=name,
                blob_id=hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest())
                for name, raw in files.items()]
    tokenizer_sibling = next(item for item in siblings if item.rfilename == "tokenizer.json")
    if storage != "git_blob":
        raw = files["tokenizer.json"]
        metadata = {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
        tokenizer_sibling.lfs = metadata if storage == "lfs_dict" else SimpleNamespace(**metadata)
        tokenizer_sibling.blob_id = "f" * 40  # Pointer blob, deliberately not the payload Git hash.

    class HubFixture:
        def model_info(self, model_id, **kwargs):
            assert model_id == p.pins.MODEL_ID
            assert kwargs == {"revision": p.pins.MODEL_REVISION, "files_metadata": True}
            return SimpleNamespace(sha=p.pins.MODEL_REVISION, siblings=siblings)

    def snapshot(**kwargs):
        assert kwargs["repo_id"] == p.pins.MODEL_ID and kwargs["revision"] == p.pins.MODEL_REVISION
        assert kwargs["allow_patterns"] == list(p.TOKENIZER_FILES)
        assert all(name.endswith(".json") for name in kwargs["allow_patterns"])
        assert "*.safetensors" in kwargs["ignore_patterns"]
        return str(tmp_path)

    def tokenizer(path, **kwargs):
        assert path == tmp_path
        assert kwargs == {"local_files_only": True, "trust_remote_code": False}
        return TokenizerFixture()

    monkeypatch.setattr(huggingface_hub, "HfApi", HubFixture)
    monkeypatch.setattr(huggingface_hub, "snapshot_download", snapshot)
    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", tokenizer)
    artifact = p.download_token_bindings(tmp_path / "cache")
    assert len(artifact["cases"]) == 152
    for name, raw in files.items():
        assert artifact["tokenizer_files"][name]["sha256"] == hashlib.sha256(raw).hexdigest()
    saved = artifact["tokenizer_files"]["tokenizer.json"]
    assert saved["storage"] == ("git_blob" if storage == "git_blob" else "lfs")
    assert saved["git_blob_sha1"] == tokenizer_sibling.blob_id
    if storage != "git_blob":
        if storage == "lfs_dict":
            tokenizer_sibling.lfs["size"] += 1
        else:
            tokenizer_sibling.lfs.size += 1
        with pytest.raises(ValueError, match="pinned LFS payload"):
            p.download_token_bindings(tmp_path / "cache")
        if storage == "lfs_dict":
            tokenizer_sibling.lfs["size"] -= 1
        else:
            tokenizer_sibling.lfs.size -= 1
    # A stale/corrupted cached file cannot be represented as the pinned tokenizer.
    (tmp_path / "tokenizer.json").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="pinned (Git blob|LFS payload)"):
        p.download_token_bindings(tmp_path / "cache")
