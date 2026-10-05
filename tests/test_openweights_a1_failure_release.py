"""Offline regression checks of the exact public A1 interruption, not new data."""

from collections import Counter
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess

import pytest

from experiments import openweights_a1_failure_release as release
from experiments.openrouter_swap import analysis as common_analysis, protocol as common
from experiments.openrouter_swap.ledger import Halted, read_events


PUBLIC = (Path(__file__).resolve().parents[1] / "data/openrouter_swap_openweights_a1"
          / "initial_failure_v1_20261004")
RAW_SHA = "ee84f0d4e6387c261ad35ce7b35be1c6a05f3e11a011c33e40ba2e65930e6ef6"
PREFIX_SHA = "27578cb69129f0486b78565a3d8c29e2e241768148457fcab37cb04b767a4443"
CAPPED = {"openweights-screen-mistral-02-final-SH", "openweights-screen-mistral-01-final-HS"}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def hashes(root):
    return {p.relative_to(root).as_posix(): sha(p.read_bytes())
            for p in root.rglob("*") if p.is_file()}


def write_json(path, value):
    path.write_text(common.canonical(value) + "\n", encoding="utf-8")


def rehash_manifest(root):
    """Rehash disposable tampered copies, never the original public bundle."""
    manifest = load(root / "MANIFEST.json")
    manifest["files"] = [{"path": p.relative_to(root).as_posix(),
                          "bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
                         for p in sorted(root.rglob("*"))
                         if p.is_file() and p.name != "MANIFEST.json"]
    write_json(root / "MANIFEST.json", manifest)


@pytest.fixture(scope="module", autouse=True)
def offline_only():
    original = subprocess.check_output

    def forbidden(*args, **kwargs):
        raise AssertionError("Network, credentials and paid dispatch are forbidden")

    def local_git(args, **kwargs):
        assert args[:2] in (["git", "show"], ["git", "merge-base"])
        return original(args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        patch.setattr(release.prod, "load_key", forbidden)
        patch.setattr(subprocess, "check_output", local_git)
        yield


@pytest.fixture(scope="module")
def public_release():
    assert (PUBLIC / "MANIFEST.json").is_file(), "The completed public bundle is required"
    before = hashes(PUBLIC)
    yield PUBLIC
    assert hashes(PUBLIC) == before


@pytest.fixture
def copy_release(public_release, tmp_path):
    return shutil.copytree(public_release, tmp_path / "release")


def test_actual_public_release_verifies_without_changing_bytes(public_release):
    assert release.verify(public_release) == {"pass": True, "status": "incomplete", "files": 12}
    metadata = load(public_release / "RELEASE.json")
    assert metadata["schema"] == "openweights-a1-interrupted-release-v1"
    assert metadata["freeze"] == "9407bae95d759de4f64b4f34d03281164f4ecae9"
    assert metadata["plan_sha256"] == "caa54bbe9aae1fa7ff43427cbb74f2d669c5c48b9e299033980f4187ff33b667"
    assert metadata["audit"]["calls"] == 92
    assert metadata["audit"]["unresolved"] == 0
    assert metadata["fixtures_pass"] is True
    assert metadata["collection_complete"] == {"screen": False, "main": False}
    assert metadata["endpoint_complete"] is False
    assert metadata["admitted_models"] == []
    assert metadata["primary_family_size"] == 4
    assert "tests/test_openweights_a1_failure_release.py" not in load(public_release / "PLAN.json")["source_hashes"]
    assert metadata["costs"] == {
        "extension_cost_bound_usd": "1.84767560", "prior_cost_bound_usd": "84.64275336",
        "external_completion_commitments_usd": "0", "scope_cost_plus_commitments_usd": "86.49042896"}
    repair = metadata["publication_repair"]
    assert repair["post_outcome"] is True and repair["original_receipts_changed"] is False
    assert repair["new_model_calls"] == 0
    assert repair["status"] == "technical_interruption_not_completed_screen"
    assert repair["raw_journal_sha256"] == RAW_SHA
    assert repair["fixture_prefix"] == {"event_count": 53, "sha256": PREFIX_SHA}


def test_capped_and_unrun_rows_remain_missing(public_release):
    screen = load(public_release / "screen_rows.json")
    assert len(screen) == 96
    assert {row["id"] for row in screen if row["cap_hit"]} == CAPPED
    for row in screen:
        if row["id"] in CAPPED:
            assert row["status"] == "incomplete"
            assert row["response"] is None and row["labels"] == {}
        if row["status"] == "not_generated":
            assert row["response"] is None and row["labels"] == {}
    assert Counter((r["model"], r["status"]) for r in screen) == {
        ("qwen", "ok"): 8, ("qwen", "not_generated"): 40,
        ("mistral", "ok"): 4, ("mistral", "incomplete"): 2, ("mistral", "not_generated"): 42}
    analysis = load(public_release / "screen_analysis.json")
    for model, expected in (("qwen", {"SS": 2, "HH": 2, "SH": 2, "HS": 2}),
                            ("mistral", {"SS": 1, "HH": 1, "SH": 0, "HS": 1})):
        for judge in analysis["models"][model]["judges"].values():
            for instrument in judge.values():
                for cell, observed in expected.items():
                    summary = instrument["cells"][cell]
                    assert (summary["planned"], summary["observed"], summary["missing"]) == (12, observed, 12-observed)
                    if observed == 0:
                        assert summary["proportion"] is None
    main = load(public_release / "main_rows.json")
    assert len(main) == 512
    assert all(r["status"] == "not_generated" and r["response"] is None and r["labels"] == {} for r in main)
    for model in load(public_release / "main_analysis.json")["models"].values():
        for judge in model["judges"].values():
            for instrument in judge.values():
                assert all(c["observed"] == 0 and c["missing"] == 32 and c["proportion"] is None
                           for c in instrument["cells"].values())
                for name in common_analysis.PRIMARY_CONTRASTS:
                    contrast = instrument["contrasts"][name]
                    assert contrast["complete_blocks"] == 0 and contrast["missing_blocks"] == 32
                    assert contrast["complete_case_mean"] is None


def test_prefix_pass_is_all_26_fixtures_not_a_retrospective_full_run_gate(public_release, tmp_path):
    raw = gzip.decompress((public_release / "raw/events.jsonl.gz").read_bytes())
    assert sha(raw) == RAW_SHA
    journal = tmp_path / "events.jsonl"
    journal.write_bytes(raw)
    events = read_events(journal)
    assert len(events) == 185
    prefix = events[:53]
    assert Counter(e["kind"] for e in prefix) == {"binding": 1, "reserve": 26, "settle": 26}
    assert all(e["data"]["phase"] == "fixtures" for e in prefix if e["kind"] == "reserve")
    assert events[53]["kind"] == "reserve" and events[53]["data"]["phase"] == "screen"
    settlements = [e["data"] for e in events if e["kind"] == "settle"]
    assert len(settlements) == 92 and all(d["status"] == "settled" for d in settlements)
    over = [d for d in settlements if d["over_reservation"]]
    assert len(over) == 1 and over[0]["call_id"] == "gen:openweights-screen-mistral-02-final-SH"
    assert Decimal(over[0]["cost_usd"]) == Decimal("0.0741945")
    usage = over[0]["raw"]["usage"]
    assert usage["completion_tokens"] == 4096
    assert usage["completion_tokens_details"]["reasoning_tokens"] == 5764
    assert Decimal(str(usage["cost"])) == Decimal("0.0309645")
    reserve = next(e["data"] for e in events if e["kind"] == "reserve"
                   and e["data"]["call_id"] == over[0]["call_id"])
    assert Decimal(reserve["cost_usd"]) == Decimal("0.06927")
    plan, runtime = load(public_release / "PLAN.json"), load(public_release / "runtime.json")
    gate, evidence = release.fixture_prefix(raw, events, plan, runtime)
    assert evidence == {"event_count": 53, "sha256": PREFIX_SHA}
    assert gate == load(public_release / "fixture_gate.json")
    assert gate["pass"] is True and len(gate["rows"]) == 24
    assert len(gate["routes"]) == 2 and all(r["pass"] for r in gate["routes"])
    cap, screen = release.protocol.Budget(**plan["budget"]).limits()
    with release.SharedLedger(tmp_path, cap=cap, screen_cap=screen) as ledger:
        runner = release.ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger)
        with pytest.raises(Halted, match="over-reservation"):
            runner.require_fixtures()
    assert journal.read_bytes() == raw


@pytest.mark.parametrize("rehash", [False, True])
def test_raw_tamper_rejected_even_with_updated_manifest(copy_release, rehash):
    path = copy_release / "raw/events.jsonl.gz"
    path.write_bytes(gzip.compress(gzip.decompress(path.read_bytes()) + b"\n", mtime=0))
    if rehash:
        rehash_manifest(copy_release)
    with pytest.raises(Halted, match="preserved A1 failure journal" if rehash else "Manifest inventory"):
        release.verify(copy_release)


@pytest.mark.parametrize("name", sorted(release.DERIVED))
def test_rehashed_derived_tamper_is_reconstructed(copy_release, name):
    path = copy_release / name
    value = load(path)
    if name == "RELEASE.json":
        value["costs"]["extension_cost_bound_usd"] = "0"
    elif name == "qualification.json":
        value["eligible_models"] = ["mistral"]
    elif name.endswith("_rows.json"):
        row = next((r for r in value if r["id"] in CAPPED), value[0])
        row.update(status="ok", cap_hit=False, response="Tampered disposable test copy")
    else:
        cell = value["models"]["mistral"]["judges"]["astra"]["inclusive_current_assertion"]["cells"]["SH"]
        cell.update(observed=1, negative=1, missing=cell["planned"]-1, proportion=0.0)
    write_json(path, value)
    rehash_manifest(copy_release)
    with pytest.raises(Halted, match="Derived release payload does not reconstruct"):
        release.verify(copy_release)


def test_rehashed_fixture_gate_tamper_is_replayed(copy_release):
    path = copy_release / "fixture_gate.json"
    gate = load(path)
    gate["rows"].pop()
    write_json(path, gate)
    rehash_manifest(copy_release)
    with pytest.raises(Halted, match="Fixture result differs from raw receipts"):
        release.verify(copy_release)


def test_extra_file_cannot_be_laundered_into_manifest(copy_release):
    write_json(copy_release / "extra.json", {"synthetic_test": True})
    rehash_manifest(copy_release)
    with pytest.raises(Halted, match="Extra or private release payload"):
        release.verify(copy_release)


@pytest.mark.parametrize("phase", ["fixtures", "screen-initial"])
def test_missing_launch_receipt_rejected_after_rehash(copy_release, phase):
    path = next(p for p in (copy_release / "launches").glob("*.json") if load(p)["phase"] == phase)
    path.unlink()
    rehash_manifest(copy_release)
    with pytest.raises(Halted, match="preceding launch record|outside declared checkpoint"):
        release.verify(copy_release)


def test_missing_raw_settlement_rejected_with_valid_rehashed_chain(copy_release, tmp_path):
    path = copy_release / "raw/events.jsonl.gz"
    events = [json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines()]
    events.remove(next(e for e in events if e["kind"] == "settle"))
    previous, lines = None, []
    for seq, event in enumerate(events, 1):
        event.update(seq=seq, previous=previous)
        event["sha256"] = common.digest({k: v for k, v in event.items() if k != "sha256"})
        previous = event["sha256"]
        lines.append(common.canonical(event).encode() + b"\n")
    raw = b"".join(lines)
    journal = tmp_path / "tampered-events.jsonl"
    journal.write_bytes(raw)
    assert len(read_events(journal)) == 184
    path.write_bytes(gzip.compress(raw, mtime=0))
    rehash_manifest(copy_release)
    with pytest.raises(Halted, match="preserved A1 failure journal"):
        release.verify(copy_release)
