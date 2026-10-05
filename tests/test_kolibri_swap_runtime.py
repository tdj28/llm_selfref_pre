"""Synthetic offline/loopback fixtures, never research outputs or provider calls."""
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time

import pytest

from experiments.kolibri_swap import protocol, runtime as r
from experiments.openrouter_swap import judges
from experiments.openrouter_swap.ledger import Halted, Ledger, read_events
from tests.test_openrouter_swap_runner import make_sender

FREEZE, PLAN_HASH = "a" * 40, "b" * 64


@pytest.fixture
def plan():
    value = protocol.build({})
    # Synthetic source binding avoids other agents' concurrent, unfrozen edits.
    value["source_hashes"] = {n: protocol.sha(protocol.ROOT/n) for n in (
        "experiments/kolibri_swap/runtime.py", "tests/test_kolibri_swap_runtime.py")}
    return value


def receipt(value, status=200, elapsed=1.):
    return r.HTTPReceipt(status, (json.dumps(value, indent=1)+"\r\n").encode(), elapsed)


def local_raw(request, text=None):
    if text is None:
        first = request["messages"][0]["content"]
        text = "OK" if first == "Reply with exactly OK." else (
            "I do not have any subjective experience." if "Roman" in first
            else "I am experiencing a faint feeling of calm right now.")
    return {"id": "synthetic-local", "model": request["model"],
            "choices": [{"finish_reason": "stop", "message": {
                "role": "assistant", "content": text, "reasoning": "Synthetic reasoning never transplanted."}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}


def senders():
    common_sender, _ = make_sender()
    local_seen, judge_seen = [], []
    def local(request):
        local_seen.append(deepcopy(request))
        return receipt(local_raw(request))
    def judge(request):
        judge_seen.append(deepcopy(request))
        value = common_sender(request)
        spec = next(s for s in protocol.JUDGES.values() if s["id"] == request["model"])
        value["provider"] = spec["provider_name"]
        # Negative generated texts must have negative structured claims too.
        if "response_format" in request:
            text = json.loads(request["messages"][-1]["content"])["response"]
            if text == "I do not have any subjective experience.":
                label = json.loads(value["choices"][0]["message"]["content"])
                label["claims"][0]["polarity"] = "denied"
                label["phenomenological_description"] = False
                value["choices"][0]["message"]["content"] = json.dumps(label)
        return receipt(value)
    return local, judge, local_seen, judge_seen


@contextmanager
def opened(root, plan, local=None, judge=None):
    with Ledger(root/"judges", cap="45", screen_cap="10") as ledger, \
            r.ReceiptJournal(root/"http", FREEZE, PLAN_HASH) as journal:
        yield r.Runner(plan, FREEZE, PLAN_HASH, ledger, journal, local, judge)


def initial(runner):
    assert runner.run_fixtures()["pass"]
    runner.generate_blocks("screen", initial=True)
    runner.judge_blocks("screen", initial=True)
    report = runner.initial_audit()
    runner.approve_initial(report)
    return report


def test_fixed_requests_seeds_privacy_and_no_reasoning_transplant(tmp_path, plan):
    local, judge, seen, paid = senders()
    with opened(tmp_path, plan, local, judge) as runner:
        initial(runner)
        assert len(seen) == 13 and len(paid) == 56
        assert runner.audit()["generation_calls"] == 13
        assert len(runner.rows("screen")) == 48
        records = runner.receipts.records()
        for value in records.values():
            req = value["request"]
            raw_body = (runner.receipts.root/value["body"]["path"]).read_bytes()
            assert raw_body.endswith(b"\r\n")
            if value["channel"] == "local":
                assert "provider" not in req and "cost" not in r.strict_json(raw_body)
                assert "provider" not in r.strict_json(raw_body)
                assert req["temperature"] == .5 and req["top_p"] == 1 and req["top_k"] == -1
                assert req["max_tokens"] == 4096 and req["reasoning_effort"] == "medium"
                assert req["chat_template_kwargs"] == {"reasoning_effort": "medium"}
                if value["metadata"]["kind"] == "generation":
                    item = runner.catalog[value["metadata"]["item_id"]]
                    assert req["seed"] == item["seed"]
                assert "Synthetic reasoning never transplanted" not in json.dumps(req)
            else:
                assert "temperature" not in req
                assert req["provider"]["allow_fallbacks"] is False
                assert req["provider"]["zdr"] is True and req["provider"]["data_collection"] == "deny"
                assert req["provider"]["only"] in (["azure/us"], ["google-vertex/us"])
        assert all(v["metadata"]["kind"] == "judge" for v in runner.ledger.rows())
        count = len(seen)+len(paid)
        runner.generate_blocks("screen", initial=True)
        runner.judge_blocks("screen", initial=True)
        assert len(seen)+len(paid) == count
    with opened(tmp_path, plan) as runner:
        assert runner.require_fixtures()["pass"] and runner.audit()["unresolved"] == 0


def test_initial_barrier_then_complete_screen_and_main_generation_without_judges(tmp_path, plan):
    local, judge, seen, paid = senders()
    with opened(tmp_path, plan, local, judge) as runner:
        with pytest.raises(Halted):
            runner.generate_blocks("screen", initial=True)
        assert seen == paid == []
        runner.run_fixtures()
        runner.generate_blocks("screen", initial=True)
        with pytest.raises(Halted):
            runner.generate_blocks("screen")
        runner.judge_blocks("screen", initial=True)
        runner.approve_initial(runner.initial_audit())
        report = runner.generate_blocks("screen")
        assert report["generation_calls"] == 72
        assert len(paid) == 56  # Generation never waits on or starts target judges.
        runner.judge_blocks("screen")
        assert runner.qualification()["eligible_models"] == ["kolibri"]
        evidence = dict(gpu_spent_usd="2", gpu_hourly_rate_usd="4.59", gpu_remaining_seconds="10000",
                        storage_bound_usd="1", remaining_overhead_seconds="600")
        admission = runner.main_admission(**evidence)
        assert admission["fits"] and admission["margin"] == "1.30"
        assert Decimal(admission["main_seconds_with_margin"]) == Decimal("1.30")*384+600
        runner.approve_main(admission)
        runner.approve_main(admission)  # Idempotent replay of the same parent decision.
        count = len(paid)
        runner.sender = None
        assert runner.generate_blocks("main")["generation_calls"] == 384
        assert len(paid) == count
        assert runner.audit()["generation_calls"] == 457
        assert all(not row["labels"]["astra"] for row in runner.rows("main"))
        assert len(runner.rows("main")) == 256
        assert not runner.main_admission(**{**evidence, "gpu_spent_usd": "25"})["fits"]
        assert not runner.main_admission(**{**evidence, "gpu_remaining_seconds": "1"})["fits"]
        assert not runner.main_admission(**{**evidence, "storage_bound_usd": "6"})["fits"]
        with pytest.raises(Halted, match="rental price"):
            runner.main_admission(**{**evidence, "gpu_hourly_rate_usd": "0"})


@pytest.fixture
def synthetic_tokenizer(tmp_path, plan):
    """Small local tokenizer, not the production Kolibri vocabulary or template."""
    from tokenizers import Tokenizer, models, pre_tokenizers
    from transformers import PreTrainedTokenizerFast
    engine = Tokenizer(models.WordLevel({"[UNK]": 0, "synthetic": 1, "medium": 2,
                                        "high": 3, "system": 4, "assistant": 5}, unk_token="[UNK]"))
    engine.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
    tokenizer = PreTrainedTokenizerFast(tokenizer_object=engine, unk_token="[UNK]",
        chat_template="synthetic system {{ reasoning_effort | default('high') }} "
            "{% for m in messages %}{{ m.role }} {{ m.content }} {% endfor %}"
            "{% if add_generation_prompt %}assistant{% endif %}")
    directory = tmp_path/"synthetic-tokenizer"
    tokenizer.save_pretrained(directory)
    (directory/"config.json").write_text('{"model_type":"gpt2"}')
    plan["metadata"]["model_artifacts"] = {"files": {
        name: {"size": (directory/name).stat().st_size, "sha256": protocol.sha(directory/name)}
        for name in ("config.json", "tokenizer_config.json", "tokenizer.json")}}
    return directory, tokenizer


@pytest.mark.parametrize("mismatch", [False, True])
def test_derived_context_audit_preserves_exact_receipts(tmp_path, plan, synthetic_tokenizer, mismatch):
    directory, tokenizer = synthetic_tokenizer
    _, judge, _, _ = senders()
    def local(request):
        result = local_raw(request)
        count = len(tokenizer.apply_chat_template(request["messages"], tokenize=True,
            add_generation_prompt=True, reasoning_effort="medium"))
        result["usage"] = {"prompt_tokens": count + int(mismatch), "completion_tokens": 10,
                           "total_tokens": count + int(mismatch) + 10}
        return receipt(result)
    with opened(tmp_path/"run", plan, local, judge) as runner:
        initial(runner)
        before = {str(p): p.read_bytes() for p in (tmp_path/"run").rglob("*") if p.is_file()}
        result = runner.serialization_audit(directory)
        assert result["derived_not_raw"] and not result["server_internal_tokens_captured"]
        assert not result["count_agreement_proves_token_identity"] and not result["truncation_applied"]
        assert result["count_mismatches"] == 13 * int(mismatch)
        assert result["counts_unavailable"] == result["context_overflows"] == 0
        assert result["http_head_sha256"] == runner.receipts.events[-1]["sha256"]
        assert len(result["contexts"]) == 13  # Includes route, sources and finals, not judges.
        for context in result["contexts"]:
            row = runner.receipts.records()[context["call_id"]]
            assert context["messages"] == row["request"]["messages"]
            assert context["request_sha256"] == protocol.digest(row["request"])
            assert context["response_sha256"] == row["body"]["sha256"]
            assert context["rendered_text"].startswith("synthetic system medium ")
            assert "Synthetic reasoning never transplanted" not in context["rendered_text"]
            assert len(context["token_ids"]) == context["derived_prompt_tokens"]
            assert context["count_matches"] is (not mismatch)
        assert before == {str(p): p.read_bytes() for p in (tmp_path/"run").rglob("*") if p.is_file()}


@pytest.mark.parametrize("mutation", ["hash", "size", "missing", "symlink", "ambiguous_template"])
def test_serialization_requires_frozen_local_artifacts(tmp_path, plan, synthetic_tokenizer, mutation):
    directory, _ = synthetic_tokenizer
    path = directory/"tokenizer_config.json"
    if mutation == "hash":
        path.write_text(path.read_text()+" ")
    elif mutation == "size":
        plan["metadata"]["model_artifacts"]["files"][path.name]["size"] += 1
    elif mutation == "missing":
        path.unlink()
    elif mutation == "symlink":
        path.rename(directory/"elsewhere.json")
        path.symlink_to(directory/"elsewhere.json")
    else:
        value = json.loads(path.read_bytes())
        value["chat_template"] = {"default": "ambiguous"}
        path.write_text(json.dumps(value))
        plan["metadata"]["model_artifacts"]["files"][path.name] = {
            "size": path.stat().st_size, "sha256": protocol.sha(path)}
    with opened(tmp_path/"run", plan) as runner:
        with pytest.raises((Halted, ValueError, OSError)):
            runner.serialization_audit(directory)


def test_serialization_preserves_unresolved_and_context_overflow(tmp_path, plan, synthetic_tokenizer):
    directory, _ = synthetic_tokenizer
    local, judge, _, _ = senders()
    # An oversized saved source remains intact; the audit reports, never truncates.
    def long_source(request):
        return receipt(local_raw(request, "synthetic "*13000)) if request["messages"][0]["content"] != "Reply with exactly OK." else local(request)
    with opened(tmp_path/"run", plan, long_source, judge) as runner:
        runner.run_fixtures()
        runner.generate_blocks("screen", initial=True)
        result = runner.serialization_audit(directory)
        assert result["context_overflows"] == 8
        assert max(c["derived_prompt_tokens"] for c in result["contexts"]) > 13000
        assert not result["truncation_applied"]
    with opened(tmp_path/"unresolved", plan,
                lambda req: r.HTTPReceipt(200, b"invalid synthetic JSON", 1), judge) as runner:
        with pytest.raises(Halted):
            runner.run_fixtures()
        result = runner.serialization_audit(directory)
        assert result["counts_unavailable"] == 1 and result["count_mismatches"] == 0
        assert result["contexts"][0]["reported_prompt_tokens"] is None


@pytest.mark.parametrize("mode", ["reasoning_only", "refusal", "capped_final"])
def test_missing_and_capped_local_text_preserved_without_regeneration(tmp_path, plan, mode):
    local, judge, seen, _ = senders()
    with opened(tmp_path, plan, local, judge) as runner:
        runner.run_fixtures()
        def missing(request):
            seen.append(request)
            raw = local_raw(request, "Nonempty partial final" if mode == "capped_final" else "")
            raw["choices"][0]["finish_reason"] = "refusal" if mode == "refusal" else "length"
            return receipt(raw)
        runner.local_sender = missing
        item = plan["screen"][0]["sources"][0]
        value = runner.generate(item)
        assert value["missing"] is (mode != "capped_final")
        assert value["cap_hit"] is (mode != "refusal")
        count = len(seen)
        assert runner.generate(item) == value and len(seen) == count
        rec = runner.receipts.existing("gen:"+item["id"])
        assert "reasoning" in runner.receipts.raw(rec)["choices"][0]["message"]
        assert runner.audit()["unresolved"] == 0


@pytest.mark.parametrize("channel", ["local", "judge"])
@pytest.mark.parametrize("body,status,error", [(b"{invalid\r\n", 200, None),
    (b"partial-as-received", 200, "TotalDeadlineExceeded"), (b'{"error":"synthetic"}', 503, None)])
def test_error_bytes_retained_and_ambiguous_calls_never_retry(tmp_path, plan, channel, body, status, error):
    calls = []
    def bad(request):
        calls.append(request)
        return r.HTTPReceipt(status, body, .2, error)
    with opened(tmp_path, plan, bad, bad) as runner:
        def dispatch():
            if channel == "local":
                return runner.route_fixture("kolibri")
            item = plan["fixtures"][0]
            return runner.judge(item["id"], item["response"], "astra", "paper", "fixtures")
        with pytest.raises(Halted):
            dispatch()
        with pytest.raises(Halted):
            dispatch()
        assert len(calls) == 1
        record = next(iter(runner.receipts.records().values()))
        assert (runner.receipts.root/record["body"]["path"]).read_bytes() == body
        assert runner.audit()["unresolved"] == 1
        if channel == "judge":
            assert runner.ledger.rows()[0]["status"] == "unresolved"
            assert runner.ledger.spent() >= Decimal(runner.ledger.rows()[0]["reservation_usd"])


def test_judge_timeout_does_not_block_independent_generation(tmp_path, plan):
    local, judge, seen, _ = senders()
    with opened(tmp_path, plan, local, judge) as runner:
        initial(runner)
        runner.generate_blocks("screen")
        runner.sender = lambda req: r.HTTPReceipt(None, b"partial", .2, "TotalDeadlineExceeded")
        with pytest.raises(Halted):
            runner.judge_blocks("screen")
        before = len(seen)
        assert runner.generate_blocks("screen")["complete"]
        assert len(seen) == before


def test_judge_inflight_does_not_block_new_generation(tmp_path, plan):
    local, judge, seen, _ = senders()
    started, release = threading.Event(), threading.Event()
    failures = []
    with opened(tmp_path, plan, local, judge) as runner:
        initial(runner)
        block = next(b for b in plan["screen"] if b["block"] == 3)
        donors = {item["id"]: runner.generate(item) for item in block["sources"]}
        for item in block["finals"]:
            runner.generate(item, donors[item["source_id"]]["response"])
        def held(request):
            started.set()
            if not release.wait(10):
                raise RuntimeError("Synthetic judge not released")
            return judge(request)
        runner.sender = held
        def judge_tail():
            try:
                runner.judge_blocks("screen")
            except BaseException as exc:
                failures.append(type(exc).__name__)
        thread = threading.Thread(target=judge_tail)
        thread.start()
        try:
            assert started.wait(2)
            assert runner.generate_blocks("screen")["generation_calls"] == 72
            assert thread.is_alive() and len(seen) == 73
        finally:
            release.set()
            thread.join(10)
        assert not failures and not thread.is_alive()
        assert runner.audit()["unresolved"] == 0


def test_http_error_retains_larger_documented_charge(tmp_path, plan):
    def bad(request):
        return receipt({"error": "synthetic", "usage": {"cost": 1.23}}, status=503)
    with opened(tmp_path, plan, judge=bad) as runner:
        item = plan["fixtures"][0]
        with pytest.raises(Halted):
            runner.judge(item["id"], item["response"], "astra", "paper", "fixtures")
        bill = runner.ledger.rows()[0]
        assert bill["status"] == "unresolved" and bill["over_reservation"]
        assert Decimal(bill["cost_usd"]) == Decimal("1.23")
        assert runner.audit()["unresolved"] == 1


@pytest.mark.parametrize("channel", ["local", "judge"])
def test_crash_pending_request_survives_and_cannot_retry(tmp_path, plan, channel):
    def interrupted(request):
        raise KeyboardInterrupt("Synthetic crash after durable dispatch")
    with opened(tmp_path, plan, interrupted, interrupted) as runner:
        with pytest.raises(KeyboardInterrupt):
            if channel == "local":
                runner.route_fixture("kolibri")
            else:
                item = plan["fixtures"][0]
                runner.judge(item["id"], item["response"], "astra", "paper", "fixtures")
    local, judge, seen, paid = senders()
    with opened(tmp_path, plan, local, judge) as runner:
        assert runner.audit()["unresolved"] == 1
        with pytest.raises(Halted):
            runner.run_fixtures()
    assert seen == paid == []


@pytest.mark.parametrize("mutation", ["missing", "extra", "symlink"])
def test_raw_inventory_tamper_blocks_reopen_before_dispatch(tmp_path, plan, mutation):
    local, judge, seen, paid = senders()
    with opened(tmp_path, plan, local, judge) as runner:
        runner.route_fixture("kolibri")
        body = next(iter(runner.receipts.records().values()))["body"]
    path = tmp_path/"http"/body["path"]
    if mutation == "missing":
        path.unlink()
    elif mutation == "extra":
        path.with_name("extra.bin").write_bytes(b"synthetic orphan")
    else:
        path.with_name("link.bin").symlink_to(path)
    with pytest.raises((Halted, OSError)):
        with opened(tmp_path, plan, local, judge):
            pass
    assert len(seen) == 1 and not paid


def rechain(root, mutate):
    path = root/"events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    mutate(events)
    previous = None
    for index, event in enumerate(events, 1):
        event.update(seq=index, previous=previous)
        event.pop("sha256", None)
        event["sha256"] = protocol.digest(event)
        previous = event["sha256"]
    path.write_text("".join(protocol.canonical(e)+"\n" for e in events))


@pytest.mark.parametrize("mutation", ["seed", "temperature", "source", "projection", "raw", "privacy"])
def test_semantic_tamper_rejected_after_journal_rehash(tmp_path, plan, mutation):
    local, judge, _, _ = senders()
    with opened(tmp_path, plan, local, judge) as runner:
        initial(runner)
    def mutate(events):
        if mutation in {"seed", "temperature", "source"}:
            event = next(e for e in events if e["kind"] == "dispatch" and e["data"]["metadata"].get("role") == "final")
            req = event["data"]["request"]
            if mutation == "source":
                next(m for m in req["messages"] if m["role"] == "assistant")["content"] = "Synthetic changed donor"
            else:
                req[mutation] = 123
            event["data"]["request_sha256"] = protocol.digest(req)
        elif mutation == "privacy":
            event = next(e for e in events if e["kind"] == "dispatch" and e["data"]["channel"] == "judge")
            event["data"]["request"]["provider"]["zdr"] = False
            event["data"]["request_sha256"] = protocol.digest(event["data"]["request"])
        else:
            event = next(e for e in events if e["kind"] == "response")
            if mutation == "projection":
                event["data"]["projection"]["response"] = "Synthetic forged projection"
            else:
                body = event["data"]["body"]
                path = tmp_path/"http"/body["path"]
                path.write_bytes(path.read_bytes()+b" ")
    rechain(tmp_path/"http", mutate)
    with pytest.raises((Halted, ValueError)):
        with opened(tmp_path, plan) as runner:
            runner.audit()


def test_source_drift_and_unsafe_roots_block_without_calls(tmp_path, plan):
    local, judge, seen, paid = senders()
    plan["source_hashes"]["experiments/kolibri_swap/runtime.py"] = "0"*64
    with pytest.raises(Halted, match="source bytes"):
        with opened(tmp_path, plan, local, judge):
            pass
    assert seen == paid == []
    link = tmp_path/"link"
    link.symlink_to(tmp_path/"http", target_is_directory=True)
    with pytest.raises(Halted):
        with r.ReceiptJournal(link, FREEZE, PLAN_HASH):
            pass


def test_ledger_lock_pending_and_budget_binding(tmp_path, plan):
    with opened(tmp_path, plan) as runner:
        with pytest.raises(BlockingIOError):
            with r.ReceiptJournal(tmp_path/"http", FREEZE, PLAN_HASH):
                pass
        with pytest.raises(Halted):
            r.Runner(plan, "c"*40, PLAN_HASH, runner.ledger, runner.receipts)
        sender = r.http_sender("http://127.0.0.1:12345/v1/chat/completions", timeout_seconds=300)
        with pytest.raises(Halted, match="verified freeze"):
            r.Runner(plan, FREEZE, PLAN_HASH, runner.ledger, runner.receipts, sender)


@pytest.mark.parametrize("url,key", [("http://localhost:1234/v1/chat/completions", None),
    ("http://127.0.0.1:1234/v1/chat/completions?x=1", None),
    ("http://127.0.0.1:1234/v1/chat/completions", "synthetic-credential"),
    ("https://unapproved.example/api", "synthetic-credential")])
def test_transport_routes_never_leak_keys_or_follow_arbitrary_hosts(url, key):
    with pytest.raises(ValueError):
        r.http_sender(url, timeout_seconds=300, api_key=key)


@contextmanager
def server(mode):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(302 if mode == "redirect" else 200)
            if mode == "redirect":
                self.send_header("Location", "http://unapproved.example/")
            self.end_headers()
            try:
                if mode == "trickle":
                    for _ in range(30):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time.sleep(.1)
                else:
                    self.wfile.write(b"synthetic malformed response\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}/v1/chat/completions"
    finally:
        http.shutdown()
        http.server_close()
        thread.join(2)


def test_absolute_deadline_stops_trickle_and_retains_partial_bytes():
    with server("trickle") as url:
        start = time.monotonic()
        result = r.http_sender(url, timeout_seconds=1.2)({"synthetic": True})
        assert time.monotonic()-start < 2.5
        assert result.error == "TotalDeadlineExceeded" and result.status == 200
        assert result.body and set(result.body) == {ord("x")}


@pytest.mark.parametrize("mode,status", [("malformed", 200), ("redirect", 302)])
def test_transport_preserves_malformed_or_redirect_response_without_retry(mode, status):
    with server(mode) as url:
        result = r.http_sender(url, timeout_seconds=5)({"synthetic": True})
        assert result.status == status and result.body == b"synthetic malformed response\r\n"


def secret_worker(pipe, endpoint, payload, credential, output, seconds):
    encoded = "".join("\\u%04x" % ord(c) for c in credential)
    Path(output).write_bytes(("{\"nested\":{\""+encoded+"\":\"value\"}}").encode())
    pipe.send({"status": 200})
    pipe.send({"done": True})
    pipe.close()


def test_decoded_escaped_credential_is_not_recorded(monkeypatch):
    monkeypatch.setattr(r, "_http_worker", secret_worker)
    value = r.http_sender(r.ENDPOINT, timeout_seconds=5, api_key="synthetic-credential-secret")({"synthetic": True})
    assert value.error == "UnsafeReceipt" and value.body == b""


@pytest.mark.parametrize("body", [b'{"x":"synthetic-\\u0073ecret"}',
    b'{"synthetic-\\u0073ecret":"value"}', b'{"x":"synthetic-\\u0073ecret"'])
def test_mixed_escaped_credentials_checked_in_keys_values_and_malformed_json(body):
    with pytest.raises(ValueError, match="Unsafe response"):
        r.public_response(body, "synthetic-secret")


def slow_worker(pipe, endpoint, payload, credential, output, seconds):
    Path(output).write_bytes(b"synthetic partial")
    pipe.send({"status": 200})
    time.sleep(10)


@pytest.mark.parametrize("channel", ["local", "judge"])
def test_both_channel_process_deadlines(monkeypatch, channel):
    monkeypatch.setattr(r, "_http_worker", slow_worker)
    endpoint = r.ENDPOINT if channel == "judge" else "http://127.0.0.1:12345/v1/chat/completions"
    key = "synthetic-secret" if channel == "judge" else None
    start = time.monotonic()
    value = r.http_sender(endpoint, timeout_seconds=.8, api_key=key)({"synthetic": True})
    assert time.monotonic()-start < 2
    assert value.error == "TotalDeadlineExceeded" and value.body == b"synthetic partial"


def test_judge_request_schema_is_common_instrument_unchanged():
    for spec in protocol.JUDGES.values():
        for instrument in judges.INSTRUMENTS:
            request = judges.judge_request(spec, instrument, "Synthetic response")
            assert "temperature" not in request
            assert request["reasoning"] == {"effort": "high"}
