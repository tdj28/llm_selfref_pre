import json
from pathlib import Path
import shutil

import pytest

from experiments.sae_assay_diagnostic.audit_judges import read_chain
from experiments.sae_assay_diagnostic.judge import digest


def write_chain(tmp_path, **updates):
    row = {"plan_sha256": "plan", "freeze_commit": "freeze", "previous_sha256": None}
    row.update(updates)
    row["receipt_sha256"] = digest(row)
    path = tmp_path / "receipts.jsonl"
    path.write_text(json.dumps(row) + "\n")
    return path


def test_public_receipt_chain_passes_without_modification(tmp_path):
    path = write_chain(tmp_path)
    before = path.read_bytes()
    assert len(read_chain(path, "plan", "freeze")) == 1
    assert path.read_bytes() == before


@pytest.mark.parametrize("update", [{"plan_sha256": "different"},
                                    {"freeze_commit": "different"},
                                    {"previous_sha256": "missing predecessor"}])
def test_public_receipt_chain_rejects_bad_binding(tmp_path, update):
    with pytest.raises(ValueError):
        read_chain(write_chain(tmp_path, **update), "plan", "freeze")


def test_public_receipt_chain_rejects_tampering_and_truncation(tmp_path):
    path = write_chain(tmp_path)
    path.write_text(path.read_text().replace('"plan"', '"fake"'))
    with pytest.raises(ValueError, match="chain mismatch"):
        read_chain(path, "plan", "freeze")
    path = write_chain(tmp_path)
    path.write_text(path.read_text().rstrip())
    with pytest.raises(ValueError, match="Truncated"):
        read_chain(path, "plan", "freeze")


def test_reproduction_refuses_existing_output_before_reading_inputs(tmp_path):
    from experiments.sae_assay_diagnostic.reproduce import reproduce

    with pytest.raises(FileExistsError, match="fresh output"):
        reproduce("absent", "absent", "absent", "absent", tmp_path)


def test_reproduction_manifest_rejects_changed_artifact(tmp_path):
    from experiments.sae_assay_diagnostic.reproduce import verify_manifest
    from experiments.sae_assay_diagnostic.protocol import sha

    data = tmp_path / "data.txt"
    data.write_text("original")
    manifest = {"files": [{"path": data.name, "bytes": data.stat().st_size, "sha256": sha(data)}]}
    (tmp_path / "MANIFEST.json").write_text(json.dumps(manifest))
    assert verify_manifest(tmp_path, "MANIFEST.json") == manifest
    data.write_text("tampered")
    with pytest.raises(ValueError, match="artifact mismatch"):
        verify_manifest(tmp_path, "MANIFEST.json")


@pytest.fixture
def released_panel(tmp_path, monkeypatch):
    from experiments.sae_assay_diagnostic import audit_judges as module
    from experiments.sae_assay_diagnostic.protocol import sha

    root = Path("data/sae_assay_diagnostic")
    plan_path = root / "stage1_plan_20260930a/PLAN.json"
    plan = json.loads(plan_path.read_text())
    monkeypatch.setattr(module, "verify_plan", lambda path, freeze: (plan, sha(plan_path)))
    judges = tmp_path / "judges"
    shutil.copytree(root / "stage1_judges_20260930", judges)
    args = (plan_path, "711a0c8e6650e57b75e4d2a6ad76a0c5d4fab9c5", root / "stage1_20260930", judges)
    return module, args, judges


def test_full_public_panel_replays_without_writing(released_panel):
    module, args, judges = released_panel
    before = {p.name: p.read_bytes() for p in judges.iterdir()}
    result = module.audit(*args)
    assert result["complete_core"] and result["request_counts"]["all"] == 184
    assert {p.name: p.read_bytes() for p in judges.iterdir()} == before


def test_public_projection_detects_changed_row_hash(released_panel):
    module, args, judges = released_panel
    path = judges / "inputs.public.json"
    data = json.loads(path.read_text())
    row_hashes = data["records"][0]["row_hashes"]
    row_hashes[next(iter(row_hashes))] = "0" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="attestation mismatch"):
        module.audit(*args)


def test_rehashed_judgment_must_still_match_raw_response(released_panel):
    module, args, judges = released_panel
    path = judges / "judgments.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["derived"]["explicit_current_assertion"] = not rows[0]["derived"]["explicit_current_assertion"]
    previous = None
    for row in rows:
        row.pop("receipt_sha256")
        row["previous_sha256"] = previous
        row["receipt_sha256"] = digest(row)
        previous = row["receipt_sha256"]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError, match="Derived judgment differs"):
        module.audit(*args)
