"""No fixture recalibration: exact public A1 bytes remain the immutable prefix."""
from decimal import Decimal
import json
import shutil

import pytest

from experiments.bilingual_llama_a1 import judges as a1, protocol as a1_protocol
from experiments.bilingual_llama_b1 import judges as j, protocol, qualification as q


def test_inheritance_replay_is_read_only_and_needs_no_historical_git(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("historical git lookup or paid call")
    monkeypatch.setattr(a1_protocol.subprocess, "check_output", forbidden)
    monkeypatch.setattr(a1, "_live_sender", forbidden)
    root = q.ROOT / q.INHERITED_RELEASE
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    proof = q.verify_inherited_fixture_release()
    assert json.loads(json.dumps(proof)) == proof
    assert len(proof["files"]) == 6 and all(not path.startswith("/") for path in proof["files"])
    assert proof["freeze_commit"] == q.INHERITED_FREEZE and proof["plan_sha256"] == q.INHERITED_PLAN_HASH
    assert proof["gate"]["pass"] and not proof["budget_projection"]["pass"]
    assert proof["budget_projection"]["api_cap_usd"] == "120"
    assert proof["prior_gate_remains_failed"] and proof["new_fixture_calls"] == 0
    assert proof["attempts"] == proof["judgments"] == 128
    assert Decimal(proof["cumulative_pilot_cost_usd"]) == Decimal("5.951798")
    assert q.verify_inherited_fixture_release() == proof
    assert before == {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("name", ["MANIFEST.json", "AUDIT.json", *("judges/" + n for n in q.FIXTURE_JOURNALS)])
def test_release_manifest_and_every_released_file_are_hash_checked(tmp_path, monkeypatch, name):
    source = q.ROOT / q.INHERITED_RELEASE
    root = tmp_path / q.INHERITED_RELEASE
    shutil.copytree(source, root)
    path = root / name
    path.write_bytes(path.read_bytes() + b"\n")
    monkeypatch.setattr(q, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="changed"):
        q.verify_inherited_fixture_release()


def test_bootstrap_imports_exact_journals_idempotently_and_no_api(tmp_path, monkeypatch):
    monkeypatch.setattr(j, "_live_sender", lambda: pytest.fail("API client"))
    root = tmp_path / "judges"
    proof = q.bootstrap_qualified_ledger(root)
    before = {name: ((root / name).read_bytes(), (root / name).stat().st_mtime_ns) for name in q.FIXTURE_JOURNALS}
    assert q.bootstrap_qualified_ledger(root) == proof
    assert before == {name: ((root / name).read_bytes(), (root / name).stat().st_mtime_ns) for name in q.FIXTURE_JOURNALS}
    assert all(data == (q.ROOT / q.INHERITED_RELEASE / "judges" / name).read_bytes()
               for name, (data, _) in before.items())
    assert j.Ledger(root).spent("judges") == Decimal("5.951798")


def test_rootless_fixture_view_requires_literal_receipt_bytes():
    source = j.Ledger(q.ROOT / q.INHERITED_RELEASE / "judges")
    class View:
        def __init__(self):
            self._cache = {}
            self.bytes = {name: source.receipt_bytes(name) for name in j.RECEIPT_FILES}

        def receipt_bytes(self, name):
            return self.bytes[name]

        def rows(self, name):
            return source.rows(name)

        def spent(self, bucket=None):
            return source.spent(bucket)

    view = View()
    plan = {"fixtures": j.fixture_inventory(), "translation_item_ids": protocol.translation_ids()}
    state = j.validate_receipts(view, plan, "a" * 64, "b" * 40, [])
    assert len(state["finals"]) == 128 and state["spent_usd"] == 5.951798
    # Same parsed JSON and record hashes cannot stand in for the original bytes.
    view.bytes["snapshots.jsonl"] = b" " + view.bytes["snapshots.jsonl"]
    with pytest.raises(ValueError, match="prefix"):
        j.validate_receipts(view, plan, "a" * 64, "b" * 40, [])


def test_bootstrap_uses_same_nonblocking_os_lock(tmp_path):
    root = tmp_path / "judges"
    with j.Ledger(root):
        with pytest.raises(j.JudgeHalted, match="Another invocation"):
            q.bootstrap_qualified_ledger(root)
    assert not any((root / name).exists() for name in q.FIXTURE_JOURNALS)


def test_bootstrap_rejects_symlinks_and_immutable_source(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        q.bootstrap_qualified_ledger(alias)
    with pytest.raises(ValueError, match="immutable"):
        q.bootstrap_qualified_ledger(q.ROOT / q.INHERITED_RELEASE / "judges")


def test_interrupted_import_resumes_only_exact_complete_files(tmp_path):
    root = tmp_path / "judges"
    root.mkdir()
    source = q.ROOT / q.INHERITED_RELEASE / "judges"
    shutil.copyfile(source / "snapshots.jsonl", root / "snapshots.jsonl")
    q.bootstrap_qualified_ledger(root)
    assert q.verify_inherited_prefix(j.Ledger(root))["receipts_verified"]
    (root / "attempts.jsonl").write_bytes(b"partial")
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    with pytest.raises(ValueError, match="prefix"):
        q.bootstrap_qualified_ledger(root)
    assert before == {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}


@pytest.mark.parametrize("name", q.FIXTURE_JOURNALS)
def test_even_rehashed_fixture_prefix_cannot_be_rewritten(tmp_path, name):
    root = tmp_path / "judges"
    q.bootstrap_qualified_ledger(root)
    rows = j.Ledger(root).rows(name)
    rows[0]["unit_test_tamper"] = True
    previous = None
    for row in rows:
        row.pop("record_sha256")
        row["prev_sha256"] = previous
        row["record_sha256"] = previous = j.digest(row)
    path = root / name
    path.write_text("".join(j.canonical(row) + "\n" for row in rows))
    # The adversarial chain is internally valid, but not the public A1 prefix.
    assert j.Ledger(root).rows(name) == rows
    with pytest.raises(ValueError, match="prefix"):
        j.validate_receipts(j.Ledger(root), {}, "a" * 64, "b" * 40, [])
    with pytest.raises(ValueError, match="prefix"):
        q.bootstrap_qualified_ledger(root)


@pytest.mark.parametrize("name", ["requests.jsonl", "attempts.jsonl", "judgments.jsonl", "snapshots.jsonl"])
def test_extra_fixture_records_rejected_even_with_valid_hash_chain(tmp_path, name):
    root = tmp_path / "judges"
    q.bootstrap_qualified_ledger(root)
    # Explicit adversarial test injection uses frozen A1's generic append helper,
    # not B1 dispatch; production B1 append and judge_one forbid this phase.
    with a1.Ledger(root) as ledger:
        row = a1._payload(ledger.rows(name)[0])
        ledger.append(name, row)
    with pytest.raises(ValueError, match="Extra fixture"):
        j.validate_receipts(j.Ledger(root), {}, "a" * 64, "b" * 40, [])
    with pytest.raises(ValueError, match="Extra fixture"):
        q.bootstrap_qualified_ledger(root)


def test_target_append_survives_reimport_but_missing_prefix_cannot_reset(tmp_path):
    root = tmp_path / "judges"
    q.bootstrap_qualified_ledger(root)
    with j.Ledger(root) as ledger:
        j.record_snapshot(ledger, "target", [], "a" * 64, "b" * 40)
    before = {name: (root / name).read_bytes() for name in q.FIXTURE_JOURNALS}
    q.bootstrap_qualified_ledger(root)
    assert before == {name: (root / name).read_bytes() for name in q.FIXTURE_JOURNALS}
    (root / "requests.jsonl").unlink()
    with pytest.raises(ValueError, match="after ledger appends"):
        q.bootstrap_qualified_ledger(root)
    assert not (root / "requests.jsonl").exists()


def test_new_plan_binds_old_source_closure_and_all_release_bytes():
    old = a1_protocol.load_plan(q.ROOT / a1_protocol.PLAN_PATH)
    new = protocol.build_plan(old["token_bindings"])
    proof = new["amendment"]["inherited_fixture_provenance"]
    assert all(new["input_hashes"][name] == protocol.sha(protocol.ROOT / name) for name in proof["files"])
    assert new["input_hashes"][a1_protocol.PLAN_PATH] == q.INHERITED_PLAN_HASH
    assert old["source_hashes"].items() <= new["source_hashes"].items()
    changed = {key for key in old if old[key] != new[key]}
    assert changed == {"schema", "budget", "judges", "amendment", "source_hashes", "input_hashes"}
    assert new["budget"] == {**old["budget"], "api_cap_usd": "125", "contingency_usd": "15"}
    assert sum(Decimal(new["budget"][key]) for key in (
        "gpu_cap_usd", "api_cap_usd", "translation_and_storage_cap_usd", "contingency_usd")) == 200
    assert j.prior_cost_provenance()["fresh_judgments_imported"] == 0
