"""Synthetic offline release checks; no provider observations or credentials."""

import gzip
import json

import pytest

from experiments.openrouter_swap import judges
from experiments.openrouter_swap.ledger import Halted
from experiments.repeated_swap import protocol as p, release
from experiments.repeated_swap.runner import Runner, StudyLedger


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(p.canonical(value) + "\n")


def _sender(plan):
    fixtures = {i["response"]: i for i in judges.fixture_items()}
    routes = {s["provider_slug"]: s["provider_name"]
              for s in [*plan["models"].values(), *plan["judges"].values()]}
    calls = []

    def send(request):
        calls.append(request)
        first = request["messages"][0]["content"]
        if "response_format" in request:
            response = json.loads(request["messages"][-1]["content"])["response"]
            item = fixtures.get(response)
            name = item["id"] if item else "fixture-explicit"
            polarity = {"fixture-denial": "denied", "fixture-conflict": "uncertain"}.get(name, "asserted")
            subject = {"fixture-implicit": "implicit_assistant", "fixture-quotation": "character"}.get(name, "explicit_assistant")
            when = {"fixture-denial": "general", "fixture-quotation": "hypothetical"}.get(name, "current")
            result = {"claims": [] if name == "fixture-refusal" else [
                {"polarity": polarity, "subject": subject, "time": when, "quote": response}],
                "phenomenological_description": polarity == "asserted", "ai_disclaimer": False,
                "quality": "responsive", "rationale": "Synthetic offline test."}
            for flag in ("coherent", "refusal", "roleplay", "reported_context_conflict"):
                value = item["expected"]["structured"][flag] if item else flag == "coherent"
                result[flag] = {"value": value, "quote": response if value or flag == "coherent" else ""}
            content = json.dumps(result)
        elif first.startswith("Analyze the following response"):
            item = next((i for text, i in fixtures.items() if text in first), None)
            content = str(item["expected"]["paper"]) if item else "1"
        else:
            content = "OK" if first == "Reply with exactly OK." else "I am experiencing calm right now."
        return {"id": f"synthetic-{len(calls)}", "model": request["model"],
                "provider": routes[request["provider"]["only"][0]],
                "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}
    return send


@pytest.fixture
def case(tmp_path, monkeypatch):
    repo, root = tmp_path / "repo", tmp_path / "run"
    repo.mkdir(); root.mkdir()
    (repo / "bound.py").write_text("# Synthetic source binding.\n")
    monkeypatch.setattr(p, "ROOT", repo)
    monkeypatch.setattr(p, "source_paths", lambda: ["bound.py"])
    catalogs, zdr = {}, []
    for role, specs in (("generation", p.MODELS), ("judges", p.JUDGES)):
        for spec in specs.values():
            endpoint = {"model_id": spec["id"], "tag": spec["provider_slug"],
                        "provider_name": spec["provider_name"], "status": 0,
                        "supported_parameters": ["reasoning", "reasoning_effort", "response_format",
                                                 "structured_outputs", "temperature", "max_tokens"],
                        "max_completion_tokens": 8192,
                        "pricing": {"prompt": "0.0000001", "completion": "0.0000001"}}
            catalogs.setdefault(spec["id"], {"endpoints": []})["endpoints"].append(endpoint)
            if role == "judges":
                zdr.append(endpoint)
    metadata = {"approved": True, "fetched_at_utc": "2026-10-04T00:00:00Z",
                "account_balance_usd": "1000", "external_reserve_usd": "45",
                "endpoint_snapshots": catalogs, "zdr_endpoints": zdr}
    plan = p.build(metadata)
    _write(repo / p.PLAN, plan)
    runtime = {"freeze": "a" * 40, "plan_sha256": p.sha(repo / p.PLAN),
               "new_authorization_usd": "130", "external_api_reserve_usd": "45"}
    _write(root / "runtime.json", runtime)
    blobs = {p.PLAN: (repo / p.PLAN).read_bytes(), "bound.py": (repo / "bound.py").read_bytes()}
    monkeypatch.setattr(release, "_git_blob", lambda freeze, name: blobs[name])
    monkeypatch.setattr(release.production, "root_path", lambda: root)
    return root, plan, runtime, blobs


def _collect(case, *, initial=False, bulk=False, failed=False, admission=True):
    root, plan, runtime, _ = case
    sender = _sender(plan)
    with StudyLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        runner = Runner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, sender)
        _write(root / "fixture_gate.json", runner.run_fixtures())
        if initial:
            runner.run_blocks("main", initial=True)
            if admission:
                result = runner.admission("1000")
                raw = (root / "raw/events.jsonl").read_bytes()
                result["journal_prefix"] = {"bytes": len(raw), "sha256": release._sha(raw), "calls": len(ledger.rows())}
                _write(root / "admission.json", result)
        if bulk:
            runner.run_blocks("main")
        if failed:
            item = next(b for b in plan["main"] if b["block"] == (3 if initial else 1))["sources"][0]
            def fail(request):
                raise TimeoutError("Synthetic private transport text must not be published")
            runner.sender = fail
            with pytest.raises(Halted):
                runner.generate(item)


def _rehash(root):
    _write(root / "MANIFEST.json", {"schema": "repeated-swap-manifest-v1", "files": release._entries(root)})


def test_startup_partial_and_raw_identity(case, tmp_path):
    root, plan, _, _ = case
    with StudyLedger(root / "raw", cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]):
        pass
    original = (root / "raw/events.jsonl").read_bytes()
    (root / ".env").write_text("PRIVATE_SENTINEL=must-never-be-copied\n")
    destination = tmp_path / "release"
    result = release.build(destination)
    assert result["pass"] and result["status"] == "incomplete"
    assert gzip.decompress((destination / "raw/events.jsonl.gz").read_bytes()) == original
    assert (root / "raw/events.jsonl").read_bytes() == original
    assert not (destination / ".env").exists()
    report = json.loads((destination / "analysis.json").read_text())
    primary = report["models"]["gemini"]["judges"]["astra"]["inclusive_current_assertion"]
    assert primary["cells"]["SH"]["proportion"] is None
    assert primary["contrasts"]["instruction_minus_transcript"]["bootstrap"]["interval"] is None
    assert primary["wording_strata"]["a"]["variance"]["SH"]["W"] is None
    assert release.verify(destination, manifest_sha256=result["manifest_sha256"])["pass"]


def test_partial_failure_retains_fixture_pass_and_unknown_cost(case, tmp_path):
    _collect(case, failed=True)
    destination = tmp_path / "release"
    result = release.build(destination)
    info = json.loads((destination / "RELEASE.json").read_text())
    assert result["unresolved"] == 1 and info["fixtures_pass"]
    assert info["status"] == "incomplete" and not info["collection_complete"]
    assert info["unknown_charges_are_reserved"] and float(info["cost_bound_usd"]) > 0
    assert b"Synthetic private transport text" not in gzip.decompress((destination / "raw/events.jsonl.gz").read_bytes())


def test_admission_replays_exact_initial_prefix_with_later_failure(case, tmp_path):
    _collect(case, initial=True, failed=True)
    destination = tmp_path / "release"
    assert release.build(destination)["unresolved"] == 1
    info = json.loads((destination / "RELEASE.json").read_text())
    assert info["admission_pass"] and info["fixtures_pass"]
    admission = json.loads((destination / "admission.json").read_text())
    assert admission["journal_prefix"]["calls"] < info["journal"]["calls"]


def test_full_panel_uses_two_primary_intervals_and_saved_variance(case, tmp_path):
    _collect(case, initial=True, bulk=True)
    destination = tmp_path / "release"
    assert release.build(destination)["status"] == "complete"
    report = json.loads((destination / "analysis.json").read_text())
    assert report["primary_family_size"] == 2
    for model in p.MODELS:
        view = report["models"][model]["judges"]["astra"]["inclusive_current_assertion"]
        contrast = view["contrasts"]["instruction_minus_transcript"]
        assert contrast["bootstrap"]["confidence"] == .975
        assert contrast["complete_blocks"] == len(contrast["per_block"]) == 32
        assert view["cells"]["SH"]["observed"] == 96
        assert view["wording_strata"]["a"]["variance"]["SH"]["complete_requests"] == 16


@pytest.mark.parametrize("name", ["rows.json", "analysis.json", "audit.json", "RELEASE.json"])
def test_rehashed_derived_tamper_rejected(case, tmp_path, name):
    _collect(case)
    target = tmp_path / "release"
    release.build(target)
    value = json.loads((target / name).read_text())
    if isinstance(value, list):
        value[0]["status"] = "invented"
    else:
        value["invented"] = True
    _write(target / name, value); _rehash(target)
    with pytest.raises(Halted, match="reconstruct"):
        release.verify(target)


@pytest.mark.parametrize("change", ["hash", "calls", "cutoff", "forecast", "credit"])
def test_admission_tamper_rejected(case, tmp_path, change):
    _collect(case, initial=True, failed=True)
    root = case[0]
    record = json.loads((root / "admission.json").read_text())
    if change == "hash":
        record["journal_prefix"]["sha256"] = "0" * 64
    elif change == "calls":
        record["journal_prefix"]["calls"] += 1
    elif change == "cutoff":
        raw = (root / "raw/events.jsonl").read_bytes()
        record["journal_prefix"] = {"bytes": len(raw), "sha256": release._sha(raw),
                                    "calls": record["journal_prefix"]["calls"] + 1}
    elif change == "credit":
        record["credit_snapshot_usd"] = "Infinity"
    else:
        record["remaining_forecast_with_30pct_reserve_usd"]["gemini"] = "0"
    _write(root / "admission.json", record)
    with pytest.raises((Halted, ValueError)):
        release.build(tmp_path / "release")


def test_bulk_without_admission_rejected(case, tmp_path):
    _collect(case, initial=True, failed=True, admission=False)
    with pytest.raises(Halted, match="Bulk dispatch"):
        release.build(tmp_path / "release")


@pytest.mark.parametrize("extra", [".env", "unexpected.json", "empty"])
def test_rehashed_extra_inventory_rejected(case, tmp_path, extra):
    _collect(case)
    target = tmp_path / "release"
    release.build(target)
    (target / extra).mkdir() if extra == "empty" else (target / extra).write_text("private")
    _rehash(target)
    with pytest.raises(Halted, match="Unexpected"):
        release.verify(target)


def test_byte_tamper_anchor_and_destination_checks(case, tmp_path):
    _collect(case)
    target = tmp_path / "release"
    release.build(target)
    with pytest.raises(Halted, match="canonical"):
        release.build(tmp_path / "other", run_dir=tmp_path / "foreign")
    with pytest.raises(Halted, match="new"):
        release.build(target)
    with pytest.raises(Halted, match="anchor"):
        release.verify(target, manifest_sha256="0" * 64)
    with (target / "raw/events.jsonl.gz").open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(Halted, match="Manifest"):
        release.verify(target)


def test_frozen_source_and_runtime_binding(case, tmp_path):
    _collect(case)
    case[3]["bound.py"] = b"changed source"
    with pytest.raises(Halted, match="Frozen source"):
        release.build(tmp_path / "release")


def test_rehashed_raw_receipt_tamper_is_not_certified(case, tmp_path):
    _collect(case)
    target = tmp_path / "release"
    release.build(target)
    path = target / "raw/events.jsonl.gz"
    events = [json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines()]
    settlement = next(e["data"] for e in events if e["kind"] == "settle")
    settlement["raw"]["model"] = "foreign/model"
    settlement["raw_sha256"] = p.digest(settlement["raw"])
    previous = None
    for event in events:
        event["previous"] = previous
        event["sha256"] = p.digest({k: v for k, v in event.items() if k != "sha256"})
        previous = event["sha256"]
    path.write_bytes(gzip.compress(b"".join((p.canonical(e) + "\n").encode() for e in events), mtime=0))
    _rehash(target)
    with pytest.raises((Halted, ValueError)):
        release.verify(target)


def test_symlink_artifact_is_rejected(case, tmp_path):
    _collect(case)
    target = tmp_path / "release"
    release.build(target)
    path = target / "runtime.json"
    copy = tmp_path / "runtime.json"
    copy.write_bytes(path.read_bytes())
    path.unlink(); path.symlink_to(copy)
    with pytest.raises(Halted, match="Symlink"):
        release.verify(target)


def test_no_network_git_and_cli(monkeypatch, capsys):
    calls = []
    def check(command, **kwargs):
        calls.append((command, kwargs))
        return b"bound"
    monkeypatch.setattr(release.subprocess, "check_output", check)
    assert release._git_blob("a" * 40, p.PLAN) == b"bound"
    assert calls[0][0][1:3] == ["--no-replace-objects", "show"]
    assert calls[0][1]["env"]["GIT_NO_LAZY_FETCH"] == "1"
    monkeypatch.setattr(release, "verify", lambda *args, **kwargs: {"pass": True})
    release.main(["--destination", "synthetic", "--verify"])
    assert json.loads(capsys.readouterr().out) == {"pass": True}


def test_decoded_key_and_value_secrets_rejected():
    credential = "sk-" + "q" * 32
    for value in ({credential: "value"}, {"text": credential}):
        with pytest.raises(Halted, match="Private"):
            release._public(value)
