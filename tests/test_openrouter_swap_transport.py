"""Offline synthetic receipts, budget races and crash recovery; no API calls."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import traceback
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from experiments.openrouter_swap import ledger as journal
from experiments.openrouter_swap import providers
from experiments.openrouter_swap.ledger import BudgetExceeded, Halted, Ledger, read_events

ROOT = Path(__file__).resolve().parents[1]
SPEC = {"id": "synthetic/model-v1", "provider_slug": "synthetic",
        "provider_name": "Synthetic Provider", "input_price": "2", "output_price": "10",
        "reasoning_effort": "medium"}


def receipt(text=" Visible answer. ", stop="stop"):
    return {"id": "synthetic-receipt", "model": SPEC["id"], "provider": SPEC["provider_name"],
            "service_tier": "default", "choices": [{"index": 0, "finish_reason": stop,
            "message": {"role": "assistant", "content": text, "reasoning": "Private reasoning",
                        "reasoning_details": [{"type": "reasoning.text", "text": "Not the answer"}]}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300,
                      "completion_tokens_details": {"reasoning_tokens": 150}, "cost": "0.001"}}


def request():
    return providers.generation_request(SPEC, [{"role": "user", "content": "Synthetic prompt"}])


class ProviderTests(unittest.TestCase):
    def test_missing_receipt_id_rejected(self):
        raw = receipt()
        del raw["id"]
        with self.assertRaises(providers.ReceiptError):
            providers.parse_result(SPEC, raw)

    def test_request_pins_provider_prices_tier_and_parameters(self):
        body = request()
        self.assertEqual(body["provider"], {"only": ["synthetic"], "allow_fallbacks": False,
                         "require_parameters": True, "max_price": {"prompt": 2.0, "completion": 10.0}})
        self.assertEqual(body["reasoning"], {"effort": "medium"})
        self.assertEqual(body["max_tokens"], 4096)
        self.assertEqual(body["service_tier"], "default")
        self.assertIs(body["stream"], False)
        for key in ("temperature", "models", "transforms", "route", "plugins", "extra_body"):
            self.assertNotIn(key, body)
        self.assertEqual(providers.generation_request(SPEC, [], 6000)["max_tokens"], 6000)
        for cap in (True, 0, -1, 6001, 1.5, "4096"):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                providers.generation_request(SPEC, [], cap)

    def test_only_explicit_supported_temperature_and_detached_messages(self):
        for support in ({"temperature": 0.5}, {"supports_temperature": True}):
            messages = [{"role": "user", "content": "unchanged"}]
            body = providers.generation_request({**SPEC, **support}, messages)
            self.assertEqual(body["temperature"], 0.5)
            messages[0]["content"] = "changed"
            self.assertEqual(body["messages"][0]["content"], "unchanged")
        for support in ({"temperature": 1}, {"temperature": True}, {"supports_temperature": "yes"},
                        {"temperature": 0.5, "supports_temperature": False}):
            with self.subTest(support=support), self.assertRaises(ValueError):
                providers.generation_request({**SPEC, **support}, [])

    def test_price_bounds_from_plan_including_dynamic_deepseek_ceiling(self):
        for input_price, output_price in (("2", "12"), ("2", "10"), ("4", "20"),
                                          ("1.32", "3.96"), ("10", "50")):
            spec = {**SPEC, "input_price": input_price, "output_price": output_price}
            prices = providers.generation_request(spec, [])["provider"]["max_price"]
            self.assertEqual(Decimal(str(prices["prompt"])), Decimal(input_price))
            self.assertEqual(Decimal(str(prices["completion"])), Decimal(output_price))
        for bad in (None, True, "NaN", "Infinity", "-1"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                providers.generation_request({**SPEC, "input_price": bad}, [])

    def test_exact_model_provider_and_explicit_aliases(self):
        raw = receipt()
        self.assertEqual(providers.parse_result(SPEC, raw)["status"], "ok")
        for changes in ({"model": "synthetic/model-v1-2026-10-04"}, {"provider": "synthetic"},
                        {"provider": None}, {"provider": "Another Provider"}, {"model": None}):
            with self.subTest(changes=changes), self.assertRaises(providers.ReceiptError):
                providers.parse_result(SPEC, {**raw, **changes})
        alias = SPEC["id"] + "-explicit-alias"
        raw["model"] = alias
        self.assertEqual(providers.parse_result({**SPEC, "model_aliases": [alias]}, raw)["model"], alias)
        with self.assertRaises(ValueError):
            providers.parse_result({**SPEC, "model_aliases": alias}, raw)

    def test_tier_receipts_and_absent_receipt_not_silently_verified(self):
        for tier in ("flex", "fast", "priority", "ultrafast", "auto", "standard"):
            with self.subTest(tier=tier), self.assertRaises(providers.ReceiptError):
                providers.parse_result(SPEC, {**receipt(), "service_tier": tier})
        raw = receipt()
        raw.pop("service_tier")
        result = providers.parse_result(SPEC, raw)
        self.assertIsNone(result["service_tier"])
        self.assertFalse(result["service_tier_verified"])
        for suffix in ("flex", "fast", "priority", "ultrafast"):
            with self.assertRaises(ValueError):
                providers.generation_request({**SPEC, "provider_slug": "synthetic/" + suffix}, [])

    def test_only_assistant_content_is_returned_including_capped_partial_text(self):
        raw = receipt(" partial \n", "length")
        before = deepcopy(raw)
        result = providers.parse_result(SPEC, raw)
        self.assertEqual(result["response"], " partial \n")
        self.assertEqual(result["status"], "incomplete")
        self.assertTrue(result["cap_hit"])
        self.assertFalse(result["missing"])
        self.assertFalse(result["complete"])
        self.assertEqual(raw, before)
        raw["choices"][0]["message"]["content"] = [
            {"type": "reasoning", "text": "Excluded"}, {"type": "text", "text": "A"},
            {"type": "text", "text": " B"}]
        self.assertEqual(providers.parse_result(SPEC, raw)["response"], "A B")
        raw["choices"][0]["message"]["role"] = "user"
        with self.assertRaises(providers.ReceiptError):
            providers.parse_result(SPEC, raw)

    def test_reasoning_only_empty_refusal_and_absent_choice_retained(self):
        for content in (None, "", "  "):
            result = providers.parse_result(SPEC, receipt(content, "length"))
            self.assertTrue(result["cap_hit"] and result["missing"])
            self.assertNotIn("reasoning", result["response"].lower())
        raw = receipt("Kept refusal text")
        raw["choices"][0]["message"]["refusal"] = "Cannot comply"
        result = providers.parse_result(SPEC, raw)
        self.assertEqual(result["response"], "Kept refusal text")
        self.assertTrue(result["refusal"] and result["missing"])
        self.assertEqual(result["status"], "refusal")
        self.assertTrue(providers.parse_result(SPEC, {**receipt(), "choices": []})["missing"])
        self.assertTrue(providers.parse_result(SPEC, receipt("x", "content_filter"))["refusal"])

    def test_cost_counts_reasoning_once_and_takes_max_documented_cost(self):
        raw = receipt()
        self.assertEqual(providers.receipt_cost(SPEC, raw), Decimal("0.0022"))
        raw["usage"]["prompt_tokens_details"] = {"cached_tokens": 100}
        raw["usage"]["cost_details"] = {"upstream_inference_cost": "1000"}
        self.assertEqual(providers.receipt_cost(SPEC, raw), Decimal("0.0022"))
        raw["usage"]["cost"] = "0.003123456789"
        self.assertEqual(providers.receipt_cost(SPEC, raw), Decimal("0.003123456789"))
        raw["usage"].pop("cost")
        raw["usage"]["total_tokens"] = 400
        self.assertEqual(providers.receipt_cost(SPEC, raw), Decimal("0.0032"))

    def test_missing_and_invalid_usage_do_not_become_zero_cost(self):
        for usage in (None, {}, {"cost": "0.1"}, {"prompt_tokens": 1}):
            self.assertIsNone(providers.receipt_cost(SPEC, {"usage": usage}))
        for field, bad in (("prompt_tokens", True), ("completion_tokens", -1),
                           ("cost", "NaN"), ("cost", "Infinity"), ("cost", -1),
                           ("total_tokens", 100), ("completion_tokens_details", []),
                           ("completion_tokens_details", {"reasoning_tokens": 201})):
            raw = receipt()
            raw["usage"][field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                providers.receipt_cost(SPEC, raw)

    def test_utf8_input_allowance_and_total_completion_cap(self):
        body = providers.generation_request(SPEC, [{"role": "user", "content": "\u4e2d\u6587"}], 6000)
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        expected = (Decimal(len(encoded) + 4096) * 2 + Decimal(6000) * 10) / 1_000_000
        self.assertEqual(providers.reservation(SPEC, body), expected)


class TransportTests(unittest.TestCase):
    def test_one_post_exact_body_and_no_redirect(self):
        body, raw = request(), receipt()
        response = io.BytesIO(json.dumps(raw).encode())
        response.status = 200
        with patch("urllib.request.build_opener") as build:
            build.return_value.open.return_value = response
            result = providers.live_sender("inert-test-credential")(body)
        self.assertEqual(result, raw)
        self.assertEqual(build.return_value.open.call_count, 1)
        args, kwargs = build.return_value.open.call_args
        self.assertEqual(args[0].full_url, providers.ENDPOINT)
        self.assertEqual(args[0].method, "POST")
        self.assertEqual(json.loads(args[0].data), body)
        self.assertEqual(kwargs, {"timeout": 180})
        handler = build.call_args.args[0]
        self.assertIsNone(handler.redirect_request(Request(providers.ENDPOINT), None, 302,
                                                  "redirect", {}, "https://example.invalid"))

    def test_http_timeout_and_invalid_payload_never_retry_or_expose_secrets(self):
        secret = "inert-" + "private-value"
        errors = [HTTPError(providers.ENDPOINT, 429, secret, {"Authorization": secret},
                            io.BytesIO(secret.encode())), URLError(secret), TimeoutError(secret)]
        for failure in errors:
            captured = io.StringIO()
            with self.subTest(failure=type(failure).__name__), redirect_stdout(captured), redirect_stderr(captured):
                with patch("urllib.request.build_opener") as build:
                    build.return_value.open.side_effect = failure
                    try:
                        providers.live_sender(secret)(request())
                    except providers.TransportError as exc:
                        self.assertIsNone(exc.__context__)
                        self.assertNotIn(secret, "".join(traceback.format_exception(exc)))
                        self.assertNotIn(secret, repr(vars(exc)))
                    else:
                        self.fail("Expected sanitized failure")
                    self.assertEqual(build.return_value.open.call_count, 1)
            self.assertNotIn(secret, captured.getvalue())
        for payload in (secret, json.dumps({"error": {"message": secret}}),
                        json.dumps({"headers": {"Authorization": secret}}), "not-json", "[]"):
            response = io.BytesIO(payload.encode())
            response.status = 200
            with patch("urllib.request.build_opener") as build:
                build.return_value.open.return_value = response
                with self.assertRaises(providers.TransportError) as caught:
                    providers.live_sender(secret)(request())
            self.assertNotIn(secret, str(caught.exception))
            self.assertIsNone(caught.exception.__context__)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="openrouter-transport-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def reserve(self, ledger, call_id="one", amount="1", phase="main", metadata=None):
        return ledger.reserve(call_id, request(), amount, phase, metadata or {"model": "synthetic"})

    def child(self, source):
        return subprocess.run([sys.executable, "-B", "-c", source, str(self.root)], cwd=ROOT,
                              capture_output=True, text=True, timeout=20)

    def test_rows_existing_request_and_raw_replay_are_detached(self):
        body, raw, metadata = request(), receipt(), {"plan_sha256": "a" * 64}
        with Ledger(self.root) as ledger:
            self.assertIsNone(ledger.existing("one"))
            pending = ledger.reserve("one", body, "1", "main", metadata)
            self.assertEqual(pending["status"], "pending")
            self.assertEqual(pending["request_sha256"], journal.digest(body))
            body["model"] = "mutated"
            metadata["plan_sha256"] = "changed"
            pending["request"]["model"] = "also-mutated"
            self.assertEqual(ledger.existing("one")["request"], request())
            final = ledger.settle("one", raw, Decimal("0.0022"))
            self.assertEqual(final["status"], "settled")
            self.assertTrue(final["cost_known"])
            self.assertEqual(final["metadata"], {"plan_sha256": "a" * 64})
            self.assertEqual(final["raw_sha256"], journal.digest(raw))
            final["raw"]["provider"] = "mutated"
            self.assertEqual(ledger.rows()[0]["raw"], raw)
            self.assertEqual(ledger.spent(), Decimal("0.0022"))
        with Ledger(self.root) as ledger:
            self.assertEqual(ledger.existing("one")["request"], request())
            self.assertEqual(ledger.existing("one")["raw"], raw)
            self.assertEqual(ledger.spent("main"), Decimal("0.0022"))
            self.assertEqual(ledger.spent("screen"), Decimal(0))
            with self.assertRaises(Halted):
                self.reserve(ledger)
            with self.assertRaises(Halted):
                ledger.settle("one", raw, "0.0022")

    def test_concurrent_combined_screen_and_total_caps(self):
        with Ledger(self.root, cap="10", screen_cap="4") as ledger:
            def worker(index):
                try:
                    self.reserve(ledger, str(index), phase="fixtures" if index % 2 else "screen")
                    return True
                except BudgetExceeded:
                    return False
            with ThreadPoolExecutor(max_workers=12) as pool:
                self.assertEqual(sum(pool.map(worker, range(40))), 4)
            self.assertEqual(ledger.spent("fixtures") + ledger.spent("screen"), Decimal(4))
            self.reserve(ledger, "main", "6")
            self.assertEqual(ledger.spent(), Decimal(10))
            with self.assertRaises(BudgetExceeded):
                self.reserve(ledger, "exceeds", ".00000001")
        with Ledger(self.root, cap="10", screen_cap="4") as ledger:
            self.assertEqual(ledger.spent(), Decimal(10))

    def test_concurrent_main_reservations_enforce_global_cap(self):
        with Ledger(self.root, cap="5") as ledger:
            def worker(index):
                try:
                    self.reserve(ledger, str(index))
                    return True
                except BudgetExceeded:
                    return False
            with ThreadPoolExecutor(max_workers=12) as pool:
                self.assertEqual(sum(pool.map(worker, range(40))), 5)
            self.assertEqual(ledger.spent(), Decimal(5))

    def test_thread_duplicate_id_and_settlement_exactly_once(self):
        with Ledger(self.root) as ledger:
            barrier = threading.Barrier(8)
            def reserve_once(_):
                barrier.wait()
                try:
                    self.reserve(ledger)
                    return True
                except Halted:
                    return False
            with ThreadPoolExecutor(max_workers=8) as pool:
                self.assertEqual(sum(pool.map(reserve_once, range(8))), 1)
            def settle_once(_):
                try:
                    ledger.settle("one", receipt(), "0.0022")
                    return True
                except Halted:
                    return False
            with ThreadPoolExecutor(max_workers=8) as pool:
                self.assertEqual(sum(pool.map(settle_once, range(8))), 1)
        self.assertEqual([e["kind"] for e in read_events(self.root / "events.jsonl")],
                         ["binding", "reserve", "settle"])

    def test_pending_survives_real_process_crash_and_numbered_retry_adds_cost(self):
        result = self.child("""
import os, sys
from experiments.openrouter_swap.ledger import Ledger
with Ledger(sys.argv[1]) as ledger:
    ledger.reserve('one', {'model': 'synthetic'}, '1', 'screen', {'trial': 1})
    os._exit(17)
""")
        self.assertEqual(result.returncode, 17, result.stderr)
        with Ledger(self.root) as ledger:
            self.assertEqual(ledger.existing("one")["status"], "pending")
            self.assertEqual(ledger.spent(), Decimal(1))
            with self.assertRaises(Halted):
                self.reserve(ledger)
            self.reserve(ledger, "one:retry:1")
            self.assertEqual(ledger.spent(), Decimal(2))

    def test_process_lock_and_closed_context_block_mutation(self):
        with Ledger(self.root) as ledger:
            result = self.child("""
import sys
from experiments.openrouter_swap.ledger import Ledger, Halted
try:
    with Ledger(sys.argv[1]): pass
except Halted:
    sys.exit(0)
sys.exit(1)
""")
            self.assertEqual(result.returncode, 0, result.stderr)
            with self.assertRaises(Halted):
                with Ledger(self.root):
                    pass
        with self.assertRaises(Halted):
            self.reserve(ledger)

    def test_error_missing_usage_keep_reservation_and_never_error_message(self):
        secret = "inert-" + "not-for-journal"
        with Ledger(self.root) as ledger:
            self.reserve(ledger)
            row = ledger.settle("one", receipt(), "0.0022", error=TimeoutError(secret))
            self.assertEqual(row["error_type"], "TimeoutError")
            self.assertEqual(row["status"], "unresolved")
            self.assertFalse(row["cost_known"])
            for call_id, raw in (("two", None), ("three", {}), ("four", {"usage": {}})):
                self.reserve(ledger, call_id)
                row = ledger.settle(call_id, raw, 0)
                self.assertEqual(row["status"], "unresolved")
                self.assertEqual(row["cost_usd"], "1")
            self.reserve(ledger, "five")
            ledger.settle("five", None, None, error=secret)
            self.assertEqual(ledger.spent(), Decimal(5))
        self.assertNotIn(secret, (self.root / "events.jsonl").read_text())
        with Ledger(self.root) as ledger:
            self.assertEqual(ledger.spent(), Decimal(5))

    def test_overrun_retained_and_stops_dispatch_even_below_total_cap(self):
        with Ledger(self.root) as ledger:
            self.reserve(ledger)
            final = ledger.settle("one", receipt(), "2")
            self.assertTrue(final["over_reservation"])
            self.assertEqual(ledger.spent(), Decimal(2))
            with self.assertRaises(Halted):
                self.reserve(ledger, "two")
        with Ledger(self.root) as ledger:
            self.assertEqual(ledger.spent(), Decimal(2))
            with self.assertRaises(Halted):
                self.reserve(ledger, "two")

    def test_incomplete_usage_preserves_larger_documented_charge(self):
        with Ledger(self.root) as ledger:
            self.reserve(ledger)
            raw = {"usage": {"cost": "2"}}
            self.assertIsNone(providers.receipt_cost(SPEC, raw))
            row = ledger.settle("one", raw, None)
            self.assertEqual(row["status"], "unresolved")
            self.assertEqual(row["cost_usd"], "2")
            self.assertTrue(row["over_reservation"])
        with Ledger(self.root) as ledger:
            self.assertEqual(ledger.spent(), Decimal(2))

    def test_budget_binding_cannot_reset_on_restart(self):
        with Ledger(self.root):
            pass
        with self.assertRaises(Halted):
            with Ledger(self.root, cap="251"):
                pass
        with self.assertRaises(Halted):
            with Ledger(self.root, screen_cap="41"):
                pass

    def test_headers_rejected_in_request_raw_and_nested_metadata(self):
        with Ledger(self.root) as ledger:
            for value in ({"headers": {}}, {"Authorization": "inert-secret"},
                          {"nested": {"api_key": "inert-secret"}}):
                with self.assertRaises(ValueError):
                    ledger.reserve("bad", value, "1", "main", {})
                with self.assertRaises(ValueError):
                    ledger.reserve("bad", {}, "1", "main", value)
            self.reserve(ledger)
            with self.assertRaises(ValueError):
                ledger.settle("one", {"headers": {}}, "0")
            self.assertEqual(ledger.existing("one")["status"], "pending")

    def test_fsync_before_reservation_return_and_failure_latches(self):
        with Ledger(self.root) as ledger:
            original = os.fsync
            with patch.object(journal.os, "fsync", wraps=original) as sync:
                self.reserve(ledger)
                self.assertGreaterEqual(sync.call_count, 2)
            with patch.object(journal.os, "fsync", side_effect=OSError("synthetic disk failure")):
                with self.assertRaises(OSError):
                    self.reserve(ledger, "two")
            with self.assertRaises(Halted):
                self.reserve(ledger, "three")
        with Ledger(self.root) as ledger:
            self.assertEqual(ledger.existing("two")["status"], "pending")
            self.assertEqual(ledger.spent(), Decimal(2))

    def test_append_does_not_replay_whole_journal(self):
        with patch.object(journal, "read_events", wraps=read_events) as read:
            with Ledger(self.root) as ledger:
                self.assertEqual(read.call_count, 1)
                for number in range(20):
                    self.reserve(ledger, str(number))
                self.assertEqual(read.call_count, 1)
            self.assertEqual(read.call_count, 2)

    def test_hashchain_tamper_and_torn_tail_preserved(self):
        with Ledger(self.root) as ledger:
            self.reserve(ledger)
        path = self.root / "events.jsonl"
        original = path.read_bytes()
        for corrupt in (original.replace(b'"reservation_usd":"1"', b'"reservation_usd":"2"'),
                        original[:-1], original + b"broken\n", b""):
            path.write_bytes(corrupt)
            with self.assertRaises(Halted):
                with Ledger(self.root):
                    pass
            self.assertEqual(path.read_bytes(), corrupt)
        path.write_bytes(original)
        with Ledger(self.root) as ledger:
            self.assertEqual(ledger.spent(), Decimal(1))

    def test_stat_guard_and_exit_verification_detect_external_tamper(self):
        with Ledger(self.root) as ledger:
            self.reserve(ledger)
            path = self.root / "events.jsonl"
            path.write_bytes(path.read_bytes().replace(b'"reservation_usd":"1"', b'"reservation_usd":"2"'))
            with self.assertRaises(Halted):
                self.reserve(ledger, "two")
        with TemporaryDirectory() as other:
            other = Path(other).resolve()
            with self.assertRaises(Halted):
                with Ledger(other) as ledger:
                    self.reserve(ledger)
                    path = Path(other) / "events.jsonl"
                    path.write_bytes(path.read_bytes()[:-1])

    def test_rehashed_duplicate_and_inconsistent_settlement_fail_replay(self):
        with Ledger(self.root) as ledger:
            self.reserve(ledger)
            ledger.settle("one", receipt(), "0.0022")
        path = self.root / "events.jsonl"
        original = read_events(path)
        variants = []
        duplicate = deepcopy(original)
        duplicate.append(deepcopy(duplicate[-1]))
        variants.append(duplicate)
        inconsistent = deepcopy(original)
        inconsistent[-1]["data"]["cost_usd"] = "0"
        variants.append(inconsistent)
        for events in variants:
            previous = None
            for number, event in enumerate(events, 1):
                event.update(seq=number, previous=previous)
                event.pop("sha256", None)
                event["sha256"] = journal.digest(event)
                previous = event["sha256"]
            path.write_text("".join(providers._canonical(e) + "\n" for e in events))
            with self.assertRaises(Halted):
                with Ledger(self.root):
                    pass

    def test_symlink_journal_is_not_followed(self):
        destination = self.root / "untouched"
        destination.write_text("untouched")
        (self.root / "events.jsonl").symlink_to(destination)
        with self.assertRaises(Halted):
            with Ledger(self.root):
                pass
        self.assertEqual(destination.read_text(), "untouched")


if __name__ == "__main__":
    unittest.main()
