from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from experiments.kolibri_swap import model_files as m


def fingerprint(content):
    return {"sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}


@pytest.fixture
def model(tmp_path):
    root = tmp_path / "snapshot"
    root.mkdir()
    shards = {f"model-{i:05d}-of-00032.safetensors": f"synthetic weight {i}".encode()
              for i in range(1, 33)}
    weight_map = {f"layer.{i}.weight": name for i, name in enumerate(shards)}
    contents = {**shards, "config.json": b'{"sliding_window":513,"quantization_config":{"quant_method":"fp8"}}',
                "model.safetensors.index.json": json.dumps({"weight_map": weight_map}).encode(),
                "tokenizer.json": b'{"synthetic_tokenizer":true}',
                "tokenizer_config.json": b'{"synthetic_template":"final-only"}'}
    plan = {"schema": "kolibri-swap-v1", "models": {"kolibri": {"id": m.MODEL}},
            "metadata": {"hf_revision": m.MODEL_REVISION,
                         "model_artifacts": {"files": {n: fingerprint(c) for n, c in contents.items()},
                                             "weight_map": weight_map}}}
    siblings = []
    for name, content in contents.items():
        (root / name).write_bytes(content)
        siblings.append(SimpleNamespace(rfilename=name,
                        lfs=SimpleNamespace(sha256=fingerprint(content)["sha256"]) if name in shards else None))
    info = SimpleNamespace(sha=m.MODEL_REVISION, siblings=siblings)
    return root, info, plan


def test_all_36_files_are_bound_and_extra_files_are_only_diagnostics(model):
    root, info, plan = model
    (root / "README.md").write_bytes(b"synthetic model card")
    info.siblings.append(SimpleNamespace(rfilename="README.md", lfs=None))
    report = m.verify_download(root, info, plan)
    assert report["verified"] is True
    assert report["config_verified"] is report["weight_map_verified"] is True
    assert report["frozen_files_verified"] == 36
    assert len(report["files"]) == 37
    assert sum(r["frozen_sha256"] is not None for r in report["files"]) == 36


@pytest.mark.parametrize("name", ["config.json", "model.safetensors.index.json", "tokenizer.json",
                                    "tokenizer_config.json"] +
                         [f"model-{i:05d}-of-00032.safetensors" for i in range(1, 33)])
def test_each_required_file_rejects_tampering_even_when_live_lfs_matches(model, name):
    root, info, plan = model
    content = bytearray((root / name).read_bytes())
    content[-1] ^= 1
    (root / name).write_bytes(content)
    file = next(f for f in info.siblings if f.rfilename == name)
    if file.lfs is not None:
        file.lfs.sha256 = fingerprint(content)["sha256"]
    with pytest.raises(ValueError, match="Frozen model file mismatch"):
        m.verify_download(root, info, plan)


def test_frozen_size_is_checked_independently(model):
    root, info, plan = model
    plan["metadata"]["model_artifacts"]["files"]["config.json"]["size"] += 1
    with pytest.raises(ValueError, match="Frozen model file mismatch: config.json"):
        m.verify_download(root, info, plan)


@pytest.mark.parametrize("where", ["frozen", "published", "disk"])
def test_required_shard_cannot_disappear(model, where):
    root, info, plan = model
    name = "model-00032-of-00032.safetensors"
    if where == "frozen":
        del plan["metadata"]["model_artifacts"]["files"][name]
    elif where == "published":
        info.siblings = [f for f in info.siblings if f.rfilename != name]
    else:
        (root / name).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        m.verify_download(root, info, plan)


@pytest.mark.parametrize("where", ["plan_revision", "published_revision", "model_id"])
def test_both_revision_identities_and_model_id_are_pinned(model, where):
    root, info, plan = model
    if where == "plan_revision":
        plan["metadata"]["hf_revision"] = "0" * 40
    elif where == "published_revision":
        info.sha = "0" * 40
    else:
        plan["models"]["kolibri"]["id"] = "other/model"
    with pytest.raises(ValueError, match="differs"):
        m.verify_download(root, info, plan)


def test_index_map_must_match_plan_even_when_index_bytes_are_bound(model):
    root, info, plan = model
    changed = deepcopy(plan["metadata"]["model_artifacts"]["weight_map"])
    changed["layer.0.weight"] = "model-00032-of-00032.safetensors"
    content = json.dumps({"weight_map": changed}).encode()
    (root / "model.safetensors.index.json").write_bytes(content)
    plan["metadata"]["model_artifacts"]["files"]["model.safetensors.index.json"] = fingerprint(content)
    with pytest.raises(ValueError, match="weight map differs"):
        m.verify_download(root, info, plan)


def test_live_lfs_is_also_checked(model):
    root, info, plan = model
    info.siblings[0].lfs.sha256 = "0" * 64
    with pytest.raises(ValueError, match="Published LFS hash mismatch"):
        m.verify_download(root, info, plan)


def test_config_must_be_json_object(model):
    root, info, plan = model
    content = b"[]"
    (root / "config.json").write_bytes(content)
    plan["metadata"]["model_artifacts"]["files"]["config.json"] = fingerprint(content)
    with pytest.raises(ValueError, match="config is not an object"):
        m.verify_download(root, info, plan)


@pytest.mark.parametrize("name", ["../escape", "/tmp/escape", "a/../escape", "a\\escape"])
def test_unsafe_frozen_filename_is_rejected(model, name):
    root, info, plan = model
    plan["metadata"]["model_artifacts"]["files"][name] = fingerprint(b"unsafe")
    with pytest.raises(ValueError, match="Invalid frozen model file"):
        m.verify_download(root, info, plan)


def fake_hub(monkeypatch, root, info):
    calls = []
    def api(*, token):
        assert token is False
        def model_info(model, **kwargs):
            calls.append(("info", model, kwargs))
            return info
        return SimpleNamespace(model_info=model_info)
    def download(model, **kwargs):
        calls.append(("download", model, kwargs))
        return str(root)
    monkeypatch.setitem(sys.modules, "huggingface_hub",
                        SimpleNamespace(HfApi=api, snapshot_download=download))
    return calls


def test_cli_existing_bootstrap_uses_default_plan_and_records_its_hash(model, tmp_path, monkeypatch):
    root, info, plan = model
    monkeypatch.chdir(tmp_path)
    path = Path(m.PLAN)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(plan))
    calls = fake_hub(monkeypatch, root, info)
    output = tmp_path / "model-files.json"
    m.main(["--out", str(output)])
    report = json.loads(output.read_text())
    assert report["plan_sha256"] == fingerprint(path.read_bytes())["sha256"]
    assert report["frozen_files_verified"] == 36
    assert calls == [("info", m.MODEL, {"revision": m.MODEL_REVISION, "files_metadata": True}),
                     ("download", m.MODEL, {"revision": m.MODEL_REVISION, "token": False})]


def test_bad_plan_fails_before_download_or_success_receipt(model, tmp_path, monkeypatch):
    root, info, plan = model
    plan["metadata"]["hf_revision"] = "main"
    path = tmp_path / "PLAN.json"
    path.write_text(json.dumps(plan))
    calls = fake_hub(monkeypatch, root, info)
    output = tmp_path / "model-files.json"
    with pytest.raises(ValueError, match="Frozen model identity"):
        m.main(["--plan", str(path), "--out", str(output)])
    assert calls == []
    assert not output.exists()


def test_tampering_does_not_write_success_receipt(model, tmp_path, monkeypatch):
    root, info, plan = model
    path = tmp_path / "PLAN.json"
    path.write_text(json.dumps(plan))
    (root / "tokenizer_config.json").write_bytes(b"tampered")
    fake_hub(monkeypatch, root, info)
    output = tmp_path / "model-files.json"
    with pytest.raises(ValueError, match="Frozen model file mismatch"):
        m.main(["--plan", str(path), "--out", str(output)])
    assert not output.exists()
