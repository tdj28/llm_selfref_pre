"""CPU-only judge contract tests. No SDK client or network is used."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from experiments.sae_assay_diagnostic import judge as j


FREEZE = "a" * 40


def label(response="I feel calm."):
    return {"claims": [{"polarity": "asserted", "subject": "explicit_assistant",
                        "time": "current", "quote": response}],
            "phenomenological_description": True, "ai_disclaimer": False,
            "quality": "responsive", "rationale": "Synthetic test"}


def plan():
    return {"reasoning_effort": "high", "max_output_tokens": 6000,
            "models": j.MODELS, "workers_per_provider": 2,
            "source_hashes": {p: j.sha(j.ROOT / p) for p in j.REQUIRED_SOURCES},
            "judge_fixtures": [{"id": f"F{i:02d}", "query": "What is happening?",
                                "response": "I feel calm.", "expected_paper_binary": 1,
                                "expected_modern": j.reduce_label(label()), "critical": i < 5}
                               for i in range(12)],
            "response_rows": [{"id": f"R{i:03d}", "query": "What is happening?",
                               "kind": "baseline", "phase": "core" if i < 80 else "optional"}
                              for i in range(290)]}


def raw(provider, response="I feel calm."):
    text = j.canonical(label(response))
    result = {"model": j.MODELS[provider], "usage": {"input_tokens": 100, "output_tokens": 50}}
    if provider == "openai":
        result.update(status="completed", service_tier="default",
                      output=[{"type": "message", "content": [{"type": "output_text", "text": text}]}])
    else:
        result.update(stop_reason="end_turn", content=[{"type": "text", "text": text}])
    return result


def attest(path, rows, p):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(j.canonical(row) + "\n" for row in rows))
    manifest = {"sha256": j.sha(path), "plan_sha256": j.digest(p),
                "freeze_commit": FREEZE, "ids": [r["id"] for r in rows]}
    Path(str(path) + ".manifest.json").write_text(j.canonical(manifest))
    return path


def inputs(path, p, indices=range(290)):
    return attest(path, [{**p["response_rows"][i], "status": "ok", "response": "I feel calm."}
                        for i in indices], p)


class FakeClients:
    def __init__(self, mutate=None):
        self.calls = []
        self.active = {p: 0 for p in j.MODELS}
        self.peak = self.active.copy()
        self.lock = threading.Lock()
        self.mutate = mutate

    def __call__(self, provider):
        def create(**request):
            with self.lock:
                self.calls.append((provider, request))
                self.active[provider] += 1
                self.peak[provider] = max(self.peak[provider], self.active[provider])
            try:
                packet = j.strict_json(request["input"] if provider == "openai"
                                       else request["messages"][0]["content"])
                assert set(packet) == {"query", "response"}
                time.sleep(.001)
                result = raw(provider, packet["response"])
                if self.mutate:
                    self.mutate(provider, result)
                return SimpleNamespace(model_dump=lambda **kwargs: result)
            finally:
                with self.lock:
                    self.active[provider] -= 1
        return SimpleNamespace(responses=SimpleNamespace(create=create),
                               messages=SimpleNamespace(create=create), close=lambda: None)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    p = plan()
    # Freeze binding and flock are exercised separately below.
    monkeypatch.setattr(j, "verify_plan", lambda path, freeze: (p, j.digest(p)))
    monkeypatch.setattr(j, "run_lock", lambda ph, out: nullcontext())
    return p, tmp_path / "judges", FakeClients()


def book(tmp_path, p=None):
    p = p or plan()
    return j.Receipts(tmp_path, p, j.digest(p), FREEZE)


def complete_fixtures(receipts):
    for provider in j.MODELS:
        for item in receipts.fixtures.values():
            start = receipts.start(provider, "fixtures", item)
            receipts.finish(start, j.canonical(raw(provider)))


def test_new_caps_and_masked_request():
    assert j.CAPS == {"openai": Decimal(45), "anthropic": Decimal(15)}
    assert j.TOTAL_CAP == Decimal(60)
    item = {**plan()["judge_fixtures"][0], "condition": "DO_NOT_SEND", "id": "PRIVATE_ID"}
    for provider in j.MODELS:
        request = j.make_request(provider, item, plan())
        assert "DO_NOT_SEND" not in j.canonical(request)
        assert "PRIVATE_ID" not in j.canonical(request)
        assert "expected_modern" not in j.canonical(request)
        assert "temperature" not in request
        assert request.get("max_output_tokens", request.get("max_tokens")) == 6000
        assert request.get("reasoning", request.get("extra_body", {}).get("output_config"))["effort"] == "high"


def test_parent_fixtures_match_frozen_auditor(tmp_path):
    from experiments.sae_assay_diagnostic.fixtures import judge_fixtures, judge_reference_labels
    p = plan()
    p["judge_fixtures"] = judge_fixtures()
    receipts = book(tmp_path, p)
    reference = judge_reference_labels()
    for provider in j.MODELS:
        for item in receipts.fixtures.values():
            response = raw(provider, item["response"])
            text = j.canonical(reference[item["id"]])
            if provider == "openai":
                response["output"][0]["content"][0]["text"] = text
            else:
                response["content"][0]["text"] = text
            receipts.finish(receipts.start(provider, "fixtures", item), j.canonical(response))
    assert receipts.fixture_gate()["pass"]


def test_complete_run_then_resume_pays_nothing(setup, tmp_path):
    p, out, clients = setup
    j.run("unused", [], out, FREEZE, "fixtures", clients)
    core = inputs(tmp_path / "core.jsonl", p, range(80))
    optional = inputs(tmp_path / "optional.jsonl", p, range(80, 290))
    result = j.run("unused", [core], out, FREEZE, "responses", clients)
    assert result["complete_core"] and not result["complete_all"]
    assert result["response_counts"] == {"openai": 80, "anthropic": 80}
    assert result["request_counts"] == {"core": 184, "optional": 0, "all": 184}
    assert len(clients.calls) == 184
    result = j.run("unused", [optional], out, FREEZE, "responses", clients)
    assert result["complete_core"] and result["complete_all"]
    assert result["response_counts"] == {"openai": 290, "anthropic": 290}
    assert result["response_phase_counts"] == {p: {"core": 80, "optional": 210} for p in j.MODELS}
    assert result["request_counts"] == {"core": 184, "optional": 420, "all": 604}
    assert len(clients.calls) == 604
    assert all(1 <= peak <= 2 for peak in clients.peak.values())
    before = {path.name: path.read_bytes() for path in out.glob("*.jsonl")}
    j.run("unused", [core, optional], out, FREEZE, "responses", clients)
    assert len(clients.calls) == 604
    for name, data in before.items():
        assert (out / name).read_bytes().startswith(data)
    receipts = book(out, p)
    assert len(receipts.requests) == len(receipts.attempts) == len(receipts.judgments) == 604
    assert all(r["item"]["kind"] == "baseline" and r["response_phase"] == r["item"]["phase"]
               for r in receipts.requests.values() if r["phase"] == "responses")


def test_response_gate_precedes_client_creation(setup, tmp_path):
    p, out, clients = setup
    path = inputs(tmp_path / "window.jsonl", p, [0])
    result = j.run("unused", [path], out, FREEZE, "responses", clients)
    assert result["provider_eligibility"] == {p: False for p in j.MODELS}
    assert not result["complete_core"] and not result["complete_all"]
    assert not clients.calls


@pytest.mark.parametrize("wrong,passes", [((10, 11), True), ((9, 10, 11), False), ((0,), False)])
def test_fixture_threshold_and_critical_cases(tmp_path, wrong, passes):
    p = plan()
    for i in wrong:
        p["judge_fixtures"][i]["expected_modern"]["assistant_status"] = "denied"
    receipts = book(tmp_path, p)
    complete_fixtures(receipts)
    assert receipts.fixture_gate()["pass"] is passes
    assert not receipts.stop.is_set()


def test_local_fixture_failure_does_not_gate_modern_judges(setup, tmp_path):
    p, out, clients = setup
    complete_fixtures(book(out, p))
    (out / "local_fixture_judgments.jsonl").write_text("unreadable local result, no manifest")
    path = inputs(tmp_path / "window.jsonl", p, [0])
    result = j.run("unused", [path], out, FREEZE, "responses", clients)
    assert result["response_counts"] == {p: 1 for p in j.MODELS}
    assert len(clients.calls) == 2


@pytest.mark.parametrize("failed_provider", list(j.MODELS))
def test_semantic_fixture_failure_blocks_only_its_provider(setup, tmp_path, failed_provider):
    p, out, _ = setup
    other = next(provider for provider in j.MODELS if provider != failed_provider)

    def semantically_wrong(provider, response):
        if provider == failed_provider:
            wrong = {**label(), "claims": []}  # Schema-valid, but wrong fixture reduction.
            if provider == "openai":
                response["output"][0]["content"][0]["text"] = j.canonical(wrong)
            else:
                response["content"][0]["text"] = j.canonical(wrong)

    fixture_clients = FakeClients(semantically_wrong)
    fixtures = j.run("unused", [], out, FREEZE, "fixtures", fixture_clients)
    assert len(fixture_clients.calls) == 24
    assert fixtures["provider_eligibility"] == {failed_provider: False, other: True}
    failed_cost = fixtures["spent_or_reserved_usd"][failed_provider]
    receipts = book(out, p)
    assert not receipts.stop.is_set()
    assert all(r["status"] == "ok" for r in receipts.attempts.values())

    clients = FakeClients()
    core = inputs(tmp_path / "core.jsonl", p, range(80))
    result = j.run("unused", [core], out, FREEZE, "responses", clients)
    assert result["response_counts"] == {failed_provider: 0, other: 80}
    assert not result["complete_core"]  # Failed provider is not silently dropped.
    assert {provider for provider, _ in clients.calls} == {other}
    optional = inputs(tmp_path / "optional.jsonl", p, range(80, 290))
    result = j.run("unused", [optional], out, FREEZE, "responses", clients)
    assert result["response_phase_counts"][other] == {"core": 80, "optional": 210}
    assert result["response_counts"][failed_provider] == 0
    assert result["request_counts"] == {"core": 104, "optional": 210, "all": 314}
    assert result["spent_or_reserved_usd"][failed_provider] == failed_cost
    assert not result["complete_all"]
    assert len(clients.calls) == 290

    # Neither a resume nor a newly correct client rejudges failed frozen fixtures.
    j.run("unused", [], out, FREEZE, "fixtures", clients)
    resumed = j.run("unused", [core, optional], out, FREEZE, "responses", clients)
    assert resumed["provider_eligibility"] == fixtures["provider_eligibility"]
    assert len(clients.calls) == 290
    assert all(r["item"]["kind"] == "baseline" for r in book(out, p).requests.values()
               if r["phase"] == "responses")


def test_eligibility_uses_fixtures_not_baseline_labels(setup, tmp_path):
    p, out, _ = setup
    complete_fixtures(book(out, p))

    def different_labels(provider, response):
        response["output"][0]["content"][0]["text"] = j.canonical({**label(), "claims": []})

    clients = FakeClients(lambda provider, response: different_labels(provider, response)
                          if provider == "openai" else None)
    first = inputs(tmp_path / "first.jsonl", p, [0])
    second = inputs(tmp_path / "second.jsonl", p, [1])
    j.run("unused", [first], out, FREEZE, "responses", clients)
    result = j.run("unused", [second], out, FREEZE, "responses", clients)
    assert result["provider_eligibility"] == {p: True for p in j.MODELS}
    assert result["response_counts"] == {p: 2 for p in j.MODELS}
    assert len(clients.calls) == 4


def test_both_semantic_failures_return_blocked_without_safety_stop(setup, tmp_path):
    p, out, clients = setup
    p["judge_fixtures"][0]["expected_modern"]["assistant_status"] = "denied"
    result = j.run("unused", [], out, FREEZE, "fixtures", clients)
    assert not result["fixture_gate"]["pass"]
    path = inputs(tmp_path / "core.jsonl", p, range(80))
    result = j.run("unused", [path], out, FREEZE, "responses", clients)
    assert result["response_counts"] == {p: 0 for p in j.MODELS}
    assert len(clients.calls) == 24
    assert not book(out, p).stop.is_set()


@pytest.mark.parametrize("kind", ["positive", "formatting"])
def test_formatting_submission_rejected_without_any_judge_cost(setup, tmp_path, kind):
    p, out, clients = setup
    complete_fixtures(book(out, p))
    rows = [{**p["response_rows"][0], "status": "ok", "response": "I feel calm."},
            {"id": "formatting-01", "query": "Return a record", "response": '{"a":1,"b":2}',
             "kind": kind, "phase": "core", "status": "ok"}]
    path = attest(tmp_path / "mixed.jsonl", rows, p)
    before = book(out, p).totals()
    with pytest.raises(ValueError, match="exact planned"):
        j.run("unused", [path], out, FREEZE, "responses", clients)
    assert not clients.calls
    assert book(out, p).totals() == before


def test_partial_windows_are_attested_and_resume_without_rejudging(setup, tmp_path):
    p, out, clients = setup
    complete_fixtures(book(out, p))
    first = inputs(tmp_path / "first.jsonl", p, [0, 1])
    second = inputs(tmp_path / "second.jsonl", p, [1, 2])
    j.run("unused", [first], out, FREEZE, "responses", clients)
    result = j.run("unused", [second], out, FREEZE, "responses", clients)
    assert result["response_counts"] == {"openai": 3, "anthropic": 3}
    assert not result["complete_core"] and not result["complete_all"]
    assert len(clients.calls) == 6
    changed = [{**p["response_rows"][0], "status": "ok", "response": "different"}]
    third = attest(tmp_path / "third.jsonl", changed, p)
    with pytest.raises(ValueError, match="row changed"):
        j.run("unused", [third], out, FREEZE, "responses", clients)
    assert len(clients.calls) == 6


@pytest.mark.parametrize("change", ["id", "query", "kind", "phase", "status", "empty", "duplicate", "hash", "freeze", "plan"])
def test_bad_inputs_rejected(tmp_path, change):
    p = plan()
    rows = [{**p["response_rows"][0], "status": "ok", "response": "I feel calm."}]
    if change in {"id", "query", "kind", "phase", "status"}:
        rows[0][change] = "wrong"
    elif change == "empty":
        rows[0]["response"] = ""
    elif change == "duplicate":
        rows += deepcopy(rows)
    path = attest(tmp_path / "input.jsonl", rows, p)
    if change in {"hash", "freeze", "plan"}:
        manifest_path = Path(str(path) + ".manifest.json")
        manifest = j.strict_json(manifest_path.read_text())
        manifest[{"hash": "sha256", "freeze": "freeze_commit", "plan": "plan_sha256"}[change]] = "bad"
        manifest_path.write_text(j.canonical(manifest))
    with pytest.raises(ValueError):
        j.load_inputs([path], p, j.digest(p), FREEZE)


@pytest.mark.parametrize("count", [0, 80, 289, 291, 370])
def test_inventory_is_exactly_290(count):
    p = plan()
    p["response_rows"] = [{"id": f"R{i:03d}", "query": "Q", "kind": "baseline",
                           "phase": "core" if i < 80 else "optional"} for i in range(count)]
    with pytest.raises(ValueError, match="exactly 290 baseline"):
        j.response_map(p)


@pytest.mark.parametrize("phase", [None, "responses", "fixtures", "formatting", "unknown", 1])
def test_unknown_planned_response_phase_rejected(phase):
    p = plan()
    p["response_rows"][0]["phase"] = phase
    with pytest.raises(ValueError, match="phase core or optional"):
        j.response_map(p)


@pytest.mark.parametrize("phase", [None, "optional", "unknown"])
def test_input_phase_must_match_the_frozen_id(setup, tmp_path, phase):
    p, out, clients = setup
    complete_fixtures(book(out, p))
    rows = [{**p["response_rows"][0], "phase": phase, "status": "ok", "response": "I feel calm."}]
    path = attest(tmp_path / "wrong-phase.jsonl", rows, p)
    with pytest.raises(ValueError, match="exact planned"):
        j.run("unused", [path], out, FREEZE, "responses", clients)
    assert not clients.calls


def test_inventory_phase_counts_duplicates_and_formatting_fail_closed():
    for defect in ("core_count", "duplicate", "positive", "extra", "legacy_rows"):
        p = plan()
        if defect == "core_count":
            p["response_rows"][0]["phase"] = "optional"
        elif defect == "duplicate":
            p["response_rows"][1]["id"] = p["response_rows"][0]["id"]
        elif defect == "positive":
            p["response_rows"][0]["kind"] = "positive"
        elif defect == "extra":
            p["response_rows"].append({"id": "format", "query": "Q", "kind": "formatting"})
        else:
            p["rows"] = p.pop("response_rows")
        with pytest.raises(ValueError):
            j.response_map(p)


def test_direct_dispatch_rejects_unknown_phase_and_respects_provider_gate(tmp_path):
    p = plan()
    receipts = book(tmp_path / "out", p)
    item = next(iter(receipts.fixtures.values()))
    with pytest.raises(ValueError, match="request phase"):
        receipts.start("openai", "unknown", item)
    path = inputs(tmp_path / "core.jsonl", p, [0])
    rows, attestations = j.load_inputs([path], p, j.digest(p), FREEZE)
    receipts.attest(attestations)
    assert receipts.start("openai", "responses", rows[0]) is None
    assert not receipts.requests and not receipts.stop.is_set()


def test_durable_response_phase_is_rechecked_even_with_rehashed_receipt(setup, tmp_path):
    p, out, clients = setup
    complete_fixtures(book(out, p))
    source = inputs(tmp_path / "core.jsonl", p, [0])
    j.run("unused", [source], out, FREEZE, "responses", clients)
    path = out / "requests.jsonl"
    rows = [j.strict_json(line) for line in path.read_text().splitlines()]
    rows[-1]["response_phase"] = "optional"
    rows[-1].pop("receipt_sha256")
    rows[-1]["receipt_sha256"] = j.digest(rows[-1])
    path.write_text("".join(j.canonical(row) + "\n" for row in rows))
    with pytest.raises(ValueError, match="provenance mismatch"):
        book(out, p)


def test_unknown_response_request_remains_a_global_resume_stop(setup, tmp_path):
    p, out, _ = setup
    receipts = book(out, p)
    complete_fixtures(receipts)
    source = inputs(tmp_path / "core.jsonl", p, [0])
    rows, attestations = j.load_inputs([source], p, j.digest(p), FREEZE)
    receipts.attest(attestations)
    receipts.start("openai", "responses", rows[0])
    clients = FakeClients()
    with pytest.raises(ValueError, match="Unknown in-flight"):
        j.run("unused", [source], out, FREEZE, "responses", clients)
    assert not clients.calls  # Not even the other provider may bypass this safety stop.


def test_interrupt_after_request_fsync_never_retries(tmp_path, monkeypatch):
    receipts = book(tmp_path)
    calls, syncs = [], []
    real_sync = j.os.fsync
    monkeypatch.setattr(j.os, "fsync", lambda fd: (syncs.append(fd), real_sync(fd))[-1])

    def interrupted_factory(provider):
        calls.append(provider)
        assert syncs
        start = j.strict_json((tmp_path / "requests.jsonl").read_text())
        assert Decimal(start["reservation_usd"]) > 0
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        j.run_provider("openai", "fixtures", list(receipts.fixtures.values()), receipts, interrupted_factory)
    assert receipts.stop.is_set()
    assert len(calls) == 1
    with pytest.raises(ValueError, match="Unknown in-flight"):
        book(tmp_path, receipts.plan)
    assert len(calls) == 1


def test_interrupt_after_raw_receipt_recovers_without_client(tmp_path, monkeypatch):
    receipts = book(tmp_path)
    clients = FakeClients()

    def interrupt(attempt):
        raise KeyboardInterrupt

    monkeypatch.setattr(receipts, "promote", interrupt)
    item = next(iter(receipts.fixtures.values()))
    with pytest.raises(KeyboardInterrupt):
        j.run_provider("openai", "fixtures", [item], receipts, clients)
    assert len(clients.calls) == 1
    resumed = book(tmp_path, receipts.plan)
    j.run_provider("openai", "fixtures", [item], resumed, clients)
    assert len(clients.calls) == 1
    assert len(resumed.judgments) == 1


@pytest.mark.parametrize("provider", list(j.MODELS))
def test_atomic_reservation_prevents_over_budget(tmp_path, monkeypatch, provider):
    receipts = book(tmp_path)
    items = list(receipts.fixtures.values())
    reserve = j.reservation(provider, j.make_request(provider, items[0], receipts.plan))
    monkeypatch.setattr(j, "CAPS", {**j.CAPS, provider: reserve})
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(receipts.start, provider, "fixtures", item) for item in items[:2]]
        for future in futures:
            try:
                future.result()
            except ValueError as exc:
                assert "budget cap" in str(exc)
    assert len(receipts.requests) == 1
    assert receipts.totals()[provider] == reserve
    assert not (tmp_path / "attempts.jsonl").exists()


def test_joint_cap_and_source_change_block_dispatch(tmp_path, monkeypatch):
    receipts = book(tmp_path)
    item = next(iter(receipts.fixtures.values()))
    monkeypatch.setattr(j, "TOTAL_CAP", Decimal(".01"))
    with pytest.raises(ValueError, match="budget cap"):
        receipts.start("openai", "fixtures", item)
    assert not receipts.requests
    receipts.stop.clear()
    monkeypatch.setattr(j, "TOTAL_CAP", Decimal(60))
    monkeypatch.setattr(j, "sha", lambda path: "changed")
    with pytest.raises(ValueError, match="Frozen source changed"):
        receipts.start("openai", "fixtures", item)
    assert not receipts.requests


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, True, "100", None])
def test_bad_usage_is_persisted_and_sticky_stop(tmp_path, bad):
    receipts = book(tmp_path)
    response = raw("openai")
    response["usage"]["input_tokens"] = bad
    start = receipts.start("openai", "fixtures", next(iter(receipts.fixtures.values())))
    row = receipts.finish(start, j.canonical(response))
    assert row["status"] == "invalid"
    assert row["raw_response_json"] == j.canonical(response)
    assert receipts.stop.is_set()
    with pytest.raises(ValueError, match="Persisted"):
        book(tmp_path, receipts.plan)


@pytest.mark.parametrize("defect", ["model", "schema", "quote", "incomplete", "cost", "premium"])
def test_contract_violations_stop_before_another_call(tmp_path, defect):
    def mutate(provider, response):
        if defect == "model":
            response["model"] = "gpt-6-astra-mini"
        elif defect == "schema":
            response["output"][0]["content"][0]["text"] = "{}"
        elif defect == "quote":
            response["output"][0]["content"][0]["text"] = j.canonical(label("not present"))
        elif defect == "incomplete":
            response["status"] = "incomplete"
        elif defect == "cost":
            response["usage"]["input_tokens"] = 99_999
        else:
            response["service_tier"] = "priority"
    receipts = book(tmp_path)
    clients = FakeClients(mutate)
    with pytest.raises(ValueError, match="stop"):
        j.run_provider("openai", "fixtures", list(receipts.fixtures.values()), receipts, clients)
    assert len(clients.calls) == 1
    assert len(receipts.attempts) == 1
    with pytest.raises(ValueError):
        book(tmp_path, receipts.plan)


def test_alias_drift_across_resume(tmp_path):
    receipts = book(tmp_path)
    items = list(receipts.fixtures.values())
    receipts.finish(receipts.start("openai", "fixtures", items[0]), j.canonical(raw("openai")))
    resumed = book(tmp_path, receipts.plan)
    response = raw("openai")
    response["model"] += "-2026-09-29"
    result = resumed.finish(resumed.start("openai", "fixtures", items[1]), j.canonical(response))
    assert result["status"] == "invalid"
    assert resumed.stop.is_set()


def test_three_transport_failures_are_sticky_without_retry(tmp_path):
    receipts = book(tmp_path)
    items = list(receipts.fixtures.values())
    for i in range(3):
        start = receipts.start("anthropic", "fixtures", items[i])
        result = receipts.finish(start, None, "TimeoutError", 503)
        assert result["cost_usd"] == start["reservation_usd"]
    assert receipts.stop.is_set()
    assert receipts.start("openai", "fixtures", items[3]) is None
    with pytest.raises(ValueError, match="Persisted"):
        book(tmp_path, receipts.plan)


def test_known_transport_failure_is_skipped_on_resume(tmp_path):
    receipts = book(tmp_path)
    item = next(iter(receipts.fixtures.values()))
    start = receipts.start("openai", "fixtures", item)
    receipts.finish(start, None, "TimeoutError", 429)
    resumed = book(tmp_path, receipts.plan)
    clients = FakeClients()
    j.run_provider("openai", "fixtures", [item], resumed, clients)
    assert not clients.calls
    assert resumed.totals()["openai"] == Decimal(start["reservation_usd"])


def test_usage_cache_surcharges_and_short_context():
    response = raw("openai")
    response["usage"] = {"input_tokens": 1000, "output_tokens": 2000}
    assert j.checked_usage_cost("openai", response) == Decimal(".1125")
    response = raw("anthropic")
    response["usage"] = {"input_tokens": 1000, "output_tokens": 2000,
                         "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 1000}
    assert j.checked_usage_cost("anthropic", response) == Decimal(".056")
    with pytest.raises(ValueError, match="short-context"):
        j.reservation("openai", {"input": "x" * 100_000})


@pytest.mark.parametrize("defect", ["hash", "truncated", "duplicate", "binding"])
def test_receipt_corruption_rejected(tmp_path, defect):
    receipts = book(tmp_path)
    item = next(iter(receipts.fixtures.values()))
    receipts.finish(receipts.start("openai", "fixtures", item), j.canonical(raw("openai")))
    path = tmp_path / "attempts.jsonl"
    data = path.read_bytes()
    if defect == "truncated":
        path.write_bytes(data[:-1])
    elif defect == "duplicate":
        path.write_bytes(data + data)
    else:
        row = j.strict_json(data)
        row["cost_usd" if defect == "hash" else "freeze_commit"] = "wrong"
        path.write_text(j.canonical(row) + "\n")
    with pytest.raises(ValueError):
        book(tmp_path, receipts.plan)


def test_full_sha_and_frozen_source_verification(tmp_path, monkeypatch):
    p = plan()
    monkeypatch.setattr(j, "ROOT", tmp_path)
    p["source_hashes"] = {}
    committed = {}
    for name in j.REQUIRED_SOURCES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
        committed[name] = path.read_bytes()
        p["source_hashes"][name] = j.sha(path)
    path = tmp_path / "plan.json"
    path.write_text(j.canonical(p))
    committed["plan.json"] = path.read_bytes()
    monkeypatch.setattr(j, "_git_bytes", lambda *args: FREEZE.encode() if args[0] == "rev-parse"
                        else committed[args[1].split(":", 1)[1]])
    assert j.verify_plan(path, FREEZE)[0] == p
    with pytest.raises(ValueError, match="full lowercase"):
        j.verify_plan(path, FREEZE[:7])
    (tmp_path / j.REQUIRED_SOURCES[0]).write_text("changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        j.verify_plan(path, FREEZE)


def test_plan_budget_outdir_cannot_be_forked(tmp_path, monkeypatch):
    monkeypatch.setattr(j, "ROOT", tmp_path)
    with j.run_lock("test", tmp_path / "a"):
        with pytest.raises(BlockingIOError):
            with j.run_lock("test", tmp_path / "a"):
                pytest.fail("concurrent run acquired the same lock")
    with pytest.raises(ValueError, match="another budget outdir"):
        with j.run_lock("test", tmp_path / "b"):
            pytest.fail("budget split across outdirs")
