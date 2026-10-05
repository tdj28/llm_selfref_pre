"""All production-shaped plans, proofs, credentials and receipts here are synthetic."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import gzip
import json
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace
from urllib import request as http

import pytest

from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.ledger import Halted, BudgetExceeded, read_events
from experiments.openrouter_swap.providers import TransportError
from experiments.openrouter_swap.release import _inventory
from experiments.openrouter_swap_openweights import production as prod, protocol as p, release
from experiments.openrouter_swap_openweights.runner import ExtensionRunner, SharedLedger
from tests.test_openrouter_openweights_protocol import budget
from tests.test_openrouter_openweights_runner import receipts


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Network forbidden")
    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(socket, "create_connection", fail)


def inputs(b):
    now = datetime.now(timezone.utc).isoformat()
    def cost(name, amount):
        return {"id": name, "cost_bound_usd": amount, "evidence_sha256": "d"*64}
    return {"authorization": {"approval_id": "synthetic-only", "approved": True, "scope": b.scope,
                              "new_target_outcomes_seen": False},
            "reconciliation": {"scope": b.scope, "confirmed": True, "as_of_utc": now,
                               "prior_costs": [cost("synthetic-prior", b.prior_spend_usd)],
                               "external_commitments": [cost("synthetic-completion", b.external_commitments_usd)]},
            "endpoint_evidence": {s["id"]: {"spec": deepcopy(s), "privacy": deepcopy(p.PRIVACY),
                                            "catalog_sha256": "e"*64, "checked_at_utc": now}
                                  for s in [*p.MODELS.values(), *p.JUDGES.values()]}}


def synthetic_plan(tmp_path, monkeypatch, b=None):
    b = b or budget()
    plan = p.finalize_plan(p.build_draft(budget=b), **inputs(b))
    assert plan["launch_authorized"] is True
    path = tmp_path / "PLAN.json"
    prod.write_once(path, plan)
    frozen = {name: (common.ROOT / name).read_bytes() for name in plan["source_hashes"]}
    frozen[prod.PLAN] = path.read_bytes()
    commands = []
    def git(args, **kwargs):
        commands.append(args)
        if args[:2] == ["git", "show"]:
            assert args[2].split(":", 1)[0] == "a"*40
            return frozen[args[2].split(":", 1)[1]]
        if args[:2] == ["git", "ls-remote"]:
            return ("a"*40 + "\t" + prod.BRANCH + "\n").encode()
        if args[:2] == ["git", "merge-base"]:
            return b""
        raise AssertionError("Unexpected Git command")
    monkeypatch.setattr(prod.subprocess, "check_output", git)
    runtime = {"freeze": "a"*40, "plan_sha256": common.sha(path), "plan_path": prod.PLAN, "budget": plan["budget"]}
    return plan, path, runtime, commands


def launch_record(root, plan, runtime, phase):
    record = {"phase": phase, "proof": {"freeze": runtime["freeze"], "branch": prod.BRANCH, "remote_head": "a"*40},
              "reconciliation": plan["reconciliation"], "plan_sha256": runtime["plan_sha256"],
              "event_count_before": len(read_events(root / "raw/events.jsonl")),
              "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    prod.write_once(root / "launches" / (common.digest(record)+".json"), record)


def fake_sender(plan, *, main=True):
    by_request = {common.canonical(v["request"]): v["raw"] for v in receipts(plan, main=main).values()}
    seen = []
    def send(request):
        seen.append(deepcopy(request))
        return deepcopy(by_request[common.canonical(request)])
    return send, seen


@pytest.mark.parametrize("change", ["approval", "scope", "unconfirmed", "amount", "stale", "endpoint", "outcomes"])
def test_finalization_requires_scope_cost_reconciliation_and_evidence(change):
    b = budget(); values = inputs(b)
    if change == "approval": values["authorization"]["approved"] = False
    if change == "scope": b = budget(scope=None)
    if change == "unconfirmed": values["reconciliation"]["confirmed"] = False
    if change == "amount": values["reconciliation"]["external_commitments"][0]["cost_bound_usd"] = "0"
    if change == "stale": values["reconciliation"]["as_of_utc"] = (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    if change == "endpoint": next(iter(values["endpoint_evidence"].values()))["privacy"]["zdr"] = False
    if change == "outcomes": values["authorization"]["new_target_outcomes_seen"] = True
    with pytest.raises(Halted):
        p.finalize_plan(p.build_draft(budget=b), **values)


@pytest.mark.parametrize("suffix", ["Z", "+00:00"])
def test_utc_timestamp_python310_compatibility(tmp_path, monkeypatch, suffix):
    now = datetime(2026, 10, 4, 12, 0, 0, 123456, tzinfo=timezone.utc)
    parsed = []
    class Python310DateTime:
        @staticmethod
        def fromisoformat(value):
            assert not value.endswith("Z")
            parsed.append(value)
            return datetime.fromisoformat(value)

        @staticmethod
        def now(tz):
            return now.astimezone(tz)
    monkeypatch.setattr(prod, "datetime", Python310DateTime)
    stamp = now.isoformat().removesuffix("+00:00") + suffix
    assert prod._date(stamp, fresh=True) == now
    assert prod._date("2026-10-04T12:00:00" + suffix) == now.replace(microsecond=0)
    for offset in (timedelta(days=-2), timedelta(seconds=1)):
        value = (now + offset).isoformat().removesuffix("+00:00") + suffix
        with pytest.raises(Halted, match="stale or future"):
            prod._date(value, fresh=True)
    values = inputs(budget())
    values["reconciliation"]["as_of_utc"] = stamp
    for evidence in values["endpoint_evidence"].values():
        evidence["checked_at_utc"] = stamp
    plan = prod.finalize(p.build_draft(budget=budget()), **values)
    runtime = {"freeze": "a"*40, "plan_sha256": common.digest(plan)}
    record = {"phase": "fixtures", "proof": {"freeze": runtime["freeze"], "branch": prod.BRANCH,
              "remote_head": "a"*40}, "reconciliation": values["reconciliation"],
              "plan_sha256": runtime["plan_sha256"], "event_count_before": 1, "checked_at_utc": stamp}
    prod.write_once(tmp_path / "launches" / (common.digest(record) + ".json"), record)
    monkeypatch.setattr(prod.subprocess, "check_output", lambda *args, **kwargs: b"")
    assert release._launches(tmp_path, plan, runtime, [{}]) == [record]
    assert parsed and all(value.endswith("+00:00") for value in parsed)


def test_git_proof_source_hashes_and_local_verify_do_not_contact_remote(tmp_path, monkeypatch):
    plan, path, _, commands = synthetic_plan(tmp_path, monkeypatch)
    prod.verify_git(path, "a"*40)
    assert not any(c[1] == "ls-remote" for c in commands)
    assert prod.verify_git(path, "a"*40, pushed=True)[1]["remote_head"] == "a"*40
    assert any(c[1] == "merge-base" for c in commands)
    changed = deepcopy(plan); changed["source_hashes"][next(iter(plan["source_hashes"]))] = "0"*64
    with pytest.raises(Halted): prod.validate(changed)
    path.write_bytes(path.read_bytes()+b"\n")
    with pytest.raises(Halted): prod.verify_git(path, "a"*40)


def test_cli_gate_precedes_key_loading_and_alternate_ledger(tmp_path, monkeypatch, capsys):
    plan, path, _, _ = synthetic_plan(tmp_path, monkeypatch)
    monkeypatch.setattr(prod, "PLAN", str(path))
    loaded = []
    monkeypatch.setattr(prod, "load_key", lambda *_: loaded.append(True))
    for args in (["--phase", "fixtures"], ["--launch", "--phase", "fixtures"],
                 ["--launch", "--phase", "fixtures", "--run-dir", str(tmp_path)]):
        with pytest.raises(SystemExit): prod.main(args)
    assert not loaded
    reconciliation = tmp_path / "reconciliation.json"
    prod.write_once(reconciliation, plan["reconciliation"])
    monkeypatch.setattr(prod, "verify_git", lambda *a, **k: (_ for _ in ()).throw(Halted("not pushed")))
    with pytest.raises(SystemExit):
        prod.main(["--launch", "--phase", "fixtures", "--freeze", "a"*40, "--approval", "synthetic-only",
                   "--reconciliation", str(reconciliation)])
    assert not loaded and "failed closed" in capsys.readouterr().err


def test_env_is_local_private_and_not_logged(tmp_path, capsys, monkeypatch):
    path = tmp_path / "main.env"
    path.write_text("OPENROUTER_API_KEY=synthetic-credential-sentinel\n")
    path.chmod(0o600)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert prod.load_key(path) == "synthetic-credential-sentinel"
    assert not __import__("os").environ.get("OPENROUTER_API_KEY")
    path.chmod(0o644)
    with pytest.raises(Halted): prod.load_key(path)
    assert "sentinel" not in str(capsys.readouterr())


@pytest.mark.parametrize("location", ["content", "nested-key", "nested-list"])
def test_decoded_escaped_credential_rejected_before_runner_receipt(tmp_path, monkeypatch, capsys, location):
    plan, _, runtime, _ = synthetic_plan(tmp_path, monkeypatch)
    credential = "synthetic-runtime-credential"
    sender, _ = fake_sender(plan, main=False)
    raw = sender(next(v["request"] for k, v in receipts(plan, main=False).items() if k == "route:qwen"))
    if location == "content":
        raw["choices"][0]["message"]["content"] = "prefix " + credential + " suffix"
    elif location == "nested-key":
        raw["extra"] = [{"prefix-" + credential: "value"}]
    else:
        raw["extra"] = [{"details": ["prefix " + credential + " suffix"]}]
    wire = json.dumps(raw).replace(credential, "".join(f"\\u{ord(c):04x}" for c in credential)).encode()
    assert credential.encode() not in wire
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return wire
    calls = []
    def open_response(*args, **kwargs):
        calls.append(True)
        return Response()
    monkeypatch.setattr(http, "build_opener", lambda *_: SimpleNamespace(open=open_response))
    # Exercise the unchanged HTTP decoder and the extension wrapper, not a fake decoder.
    with pytest.raises(TransportError) as error:
        prod.guarded_sender(credential)({})
    assert error.value.__context__ is None and error.value.__cause__ is None
    cap, screen = budget().limits()
    with SharedLedger(tmp_path / "raw", cap=cap, screen_cap=screen) as ledger:
        runner = ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger,
                                 prod.guarded_sender(credential))
        with pytest.raises(Halted): runner.route_fixture("qwen")
        row = ledger.rows()[0]
        assert row["raw"] is None and row["status"] != "settled"
        assert ledger.spent() == Decimal(row["reservation_usd"]) > 0
        with pytest.raises(Halted): runner.route_fixture("qwen")
    assert len(calls) == 2
    assert credential not in (tmp_path / "raw/events.jsonl").read_text()
    assert credential not in repr(error.value) + str(capsys.readouterr())


def test_guarded_sender_preserves_safe_decoded_receipt_identity(monkeypatch):
    raw = {"choices": [{"message": {"content": "OK"}}], "unchanged": ["metadata"]}
    monkeypatch.setattr(prod, "live_sender", lambda _: lambda request: raw)
    assert prod.guarded_sender("synthetic-runtime-credential")({}) is raw


@pytest.mark.parametrize("field", ["approval", "prior", "external", "scope"])
@pytest.mark.parametrize("unsafe", ["/Users/private/person/approval.json", r"C:\private\approval.json",
                                    "../private", "user@private.invalid", "line\nbreak"])
def test_private_metadata_rejected_before_freeze(field, unsafe):
    b = budget(scope=unsafe) if field == "scope" else budget()
    values = inputs(b)
    if field == "approval": values["authorization"]["approval_id"] = unsafe
    if field == "prior": values["reconciliation"]["prior_costs"][0]["id"] = unsafe
    if field == "external": values["reconciliation"]["external_commitments"][0]["id"] = unsafe
    with pytest.raises(Halted, match="Public identifiers"):
        prod.finalize(p.build_draft(budget=b), **values)
    if field in {"prior", "external", "scope"}:
        with pytest.raises(Halted, match="Public identifiers"):
            prod.reconcile(b, values["reconciliation"])


def test_secret_like_identifier_rejected_by_root_scanner():
    values = inputs(budget())
    values["authorization"]["approval_id"] = "sk-" + "Q7z9B2x5" * 4
    with pytest.raises(Halted, match="Public content scan"):
        prod.finalize(p.build_draft(budget=budget()), **values)


def test_atomic_shared_caps_and_future_model_holdback(tmp_path):
    with SharedLedger(tmp_path, cap="1", screen_cap="1") as ledger:
        ledger.holdback = Decimal(".4")
        def reserve(i):
            try:
                ledger.reserve(str(i), {}, ".4", "main", {})
                return True
            except BudgetExceeded:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            assert sum(pool.map(reserve, range(4))) == 1
        assert ledger.spent() == Decimal(".4")


def test_cli_initial_audit_boundary_with_synthetic_sender(tmp_path, monkeypatch):
    plan, path, _, _ = synthetic_plan(tmp_path, monkeypatch)
    root = tmp_path / "cli-run"
    monkeypatch.setattr(prod, "PLAN", str(path))
    monkeypatch.setattr(prod, "canonical_root", lambda: root)
    checked = []
    def verified(path, freeze, pushed=False):
        assert pushed and freeze == "a"*40
        checked.append(True)
        prod.validate(plan)
        return plan, {"freeze": freeze, "branch": prod.BRANCH, "remote_head": freeze}
    monkeypatch.setattr(prod, "verify_git", verified)
    monkeypatch.setattr(prod, "load_key", lambda _: "synthetic-not-a-key")
    sender, seen = fake_sender(plan, main=False)
    monkeypatch.setattr(prod, "live_sender", lambda _: sender)
    reconciliation = tmp_path / "reconciliation.json"
    prod.write_once(reconciliation, plan["reconciliation"])
    args = ["--launch", "--freeze", "a"*40, "--approval", "synthetic-only", "--reconciliation", str(reconciliation)]
    prod.main([*args, "--phase", "fixtures"])
    assert len(seen) == 26
    with pytest.raises(SystemExit): prod.main([*args, "--phase", "screen"])
    assert len(seen) == 26
    prod.main([*args, "--phase", "screen-initial"])
    assert len(seen) == 114 and len(checked) == 3
    assert (root / "PLAN.json").read_bytes() == path.read_bytes()
    assert json.loads((root / "initial_audit.json").read_text())["value"]["calls"] == 114
    malformed = plan["reconciliation"].copy()
    malformed["external_commitments"] = [{"id": "larger", "cost_bound_usd": "90", "evidence_sha256": "d"*64}]
    reconciliation.write_text(json.dumps(malformed))
    with pytest.raises(SystemExit): prod.main([*args, "--phase", "screen"])
    assert len(seen) == 114 and len(checked) == 3


def rehash(root):
    data = {"schema": "openweights-manifest-v1", "files": [
        {"path": name, "bytes": row["size"], "sha256": row["sha256"]} for name, row in sorted(_inventory(root).items())]}
    (root / "MANIFEST.json").write_text(json.dumps(data))


def test_complete_production_replay_and_release_tamper_checks(tmp_path, monkeypatch):
    plan, path, runtime, commands = synthetic_plan(tmp_path, monkeypatch)
    root = tmp_path / "run"
    prod.bytes_once(root / "PLAN.json", path.read_bytes()); prod.write_once(root / "runtime.json", runtime)
    sender, seen = fake_sender(plan)
    cap, screen = budget().limits()
    with SharedLedger(root / "raw", cap=cap, screen_cap=screen) as ledger:
        r = ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, sender)
        launch_record(root, plan, runtime, "fixtures")
        prod.write_once(root / "fixture_gate.json", r.run_fixtures())
        launch_record(root, plan, runtime, "screen-initial")
        r.run_blocks("screen", initial=True)
        assert len(seen) == 114
        initial = prod.checkpoint(root, r, "initial_audit")
        prod.write_once(root / "initial_audit.json", initial)
        launch_record(root, plan, runtime, "screen")
        r.run_blocks("screen")
        assert len(seen) == 554
        prod.verify_checkpoint((root / "raw/events.jsonl").read_bytes(), initial, plan, runtime, "initial_audit")
        prod.write_once(root / "main_admission.json", prod.checkpoint(root, r, "main_admission"))
        launch_record(root, plan, runtime, "main")
        r.run_blocks("main")
        assert len(seen) == 3370
        main_models = [r.catalog[c["metadata"]["item_id"]]["model"] for c in ledger.rows() if c["phase"] == "main"]
        assert main_models == sorted(main_models, key=["qwen", "mistral"].index)
    original_raw = (root / "raw/events.jsonl").read_bytes()
    destination = tmp_path / "release"
    assert release.build(root, destination)["status"] == "complete"
    assert release.verify(destination)["pass"]
    assert (root / "raw/events.jsonl").read_bytes() == original_raw
    assert gzip.decompress((destination / "raw/events.jsonl.gz").read_bytes()) == original_raw
    assert not any(c[1] == "ls-remote" for c in commands)
    metadata = json.loads((destination / "RELEASE.json").read_text())
    assert metadata["primary_family_size"] == 4
    assert Decimal(metadata["costs"]["scope_cost_plus_commitments_usd"]) == Decimal(metadata["audit"]["cost_bound_usd"])+30
    assert isinstance(json.loads((destination / "MANIFEST.json").read_text())["files"], list)
    with pytest.raises(Halted): release.build(root, destination)
    for name in ("RELEASE.json", "main_analysis.json", "initial_audit.json", "main_admission.json", "runtime.json", "PLAN.json"):
        original = (destination / name).read_bytes()
        (destination / name).write_text("{}")
        rehash(destination)
        with pytest.raises((Halted, KeyError)): release.verify(destination)
        (destination / name).write_bytes(original)
    extra = destination / "credentials.env"
    extra.write_text("private fixture, not a credential")
    rehash(destination)
    with pytest.raises(Halted, match="Extra"): release.verify(destination)
    extra.unlink(); rehash(destination)
    raw_path = destination / "raw/events.jsonl.gz"
    original_compressed = raw_path.read_bytes()
    raw_path.write_bytes(gzip.compress(original_raw.replace(b'"cap_usd":"70"', b'"cap_usd":"71"', 1), mtime=0))
    rehash(destination)
    with pytest.raises(Halted): release.verify(destination)
    raw_path.write_bytes(original_compressed); rehash(destination)
    manifest_path = destination / "MANIFEST.json"
    manifest_bytes = manifest_path.read_bytes()
    malformed = json.loads(manifest_bytes); malformed["files"] = {r["path"]: r for r in malformed["files"]}
    manifest_path.write_text(json.dumps(malformed))
    with pytest.raises(Halted): release.verify(destination)
    malformed = json.loads(manifest_bytes)
    malformed["files"][0]["bytes"] = float(malformed["files"][0]["bytes"])
    manifest_path.write_text(json.dumps(malformed))
    with pytest.raises(Halted): release.verify(destination)
    manifest_path.write_bytes(manifest_bytes)
    empty = destination / "extra-private-directory"
    empty.mkdir()
    with pytest.raises(Halted, match="directory"): release.verify(destination)
    empty.rmdir()
    assert release.verify(destination)["pass"]
    # Rehashing cannot turn private metadata or escaped credential-like bytes public.
    secret = "sk-" + "Q7z9B2x5" * 4
    for name in ("RELEASE.json", "PLAN.json"):
        payload = destination / name
        original = payload.read_bytes()
        changed = json.loads(original); changed["unexpected"] = secret
        payload.write_text(json.dumps(changed).replace(secret, "".join(f"\\u{ord(c):04x}" for c in secret)))
        rehash(destination)
        with pytest.raises(Halted, match="Public content scan"):
            release.verify(destination)
        payload.write_bytes(original)
    escaped = json.dumps({"nested": [{"value": secret}]}).replace(secret, "".join(f"\\u{ord(c):04x}" for c in secret)).encode()
    raw_path.write_bytes(gzip.compress(original_raw + escaped + b"\n", mtime=0))
    rehash(destination)
    with pytest.raises(Halted, match="Public content scan"):
        release.verify(destination)
    raw_path.write_bytes(original_compressed); rehash(destination)
    assert release.verify(destination)["pass"]
    live_raw = root / "raw/events.jsonl"
    unsafe_raw = original_raw + escaped + b"\n"
    live_raw.write_bytes(unsafe_raw)
    blocked = tmp_path / "blocked-release"
    with pytest.raises(Halted, match="Public content scan"):
        release.build(root, blocked)
    assert not blocked.exists() and live_raw.read_bytes() == unsafe_raw
    live_raw.write_bytes(original_raw)


def test_failed_unknown_charge_release_keeps_full_reservation(tmp_path, monkeypatch):
    plan, path, runtime, _ = synthetic_plan(tmp_path, monkeypatch)
    root = tmp_path / "run"
    prod.bytes_once(root / "PLAN.json", path.read_bytes()); prod.write_once(root / "runtime.json", runtime)
    sender, _ = fake_sender(plan)
    def unknown(request):
        raw = sender(request); raw.pop("usage")
        return raw
    cap, screen = budget().limits()
    with SharedLedger(root / "raw", cap=cap, screen_cap=screen) as ledger:
        r = ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, unknown)
        launch_record(root, plan, runtime, "fixtures")
        with pytest.raises(Halted): r.route_fixture("qwen")
        charged = ledger.spent()
    destination = tmp_path / "failed-release"
    assert release.build(root, destination)["status"] == "incomplete"
    metadata = json.loads((destination / "RELEASE.json").read_text())
    assert metadata["audit"]["unresolved"] == 1
    assert Decimal(metadata["costs"]["extension_cost_bound_usd"]) == charged > 0
