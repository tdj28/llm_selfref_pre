"""Synthetic, target-blind tests for the changepoint runtime primitives."""

from __future__ import annotations

import unittest

from experiments.consciousness_sae_changepoint.runtime_core import (
    Layer50SwitchHook,
    RuntimeContractError,
    cache_tensor_sha256,
    clone_kv_cache,
    extract_residual_positions,
    hash_uniform,
    hash_uniform_receipt,
    inverse_cdf_sample,
    resolve_probe_event_times,
)


try:
    import torch
except ImportError:  # The lightweight plan-building environment has no torch.
    torch = None


class HashDerivedNoiseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = {
            "sampling_domain_hash": "0" * 64,
            "prefix_seed": 2_026_071_302,
            "paired_stream_id": "paired-main-0007",
        }

    def test_frozen_uniform_fixture(self) -> None:
        receipt = hash_uniform_receipt(**self.key, decode_step=17)
        self.assertEqual(
            receipt.digest_sha256,
            "9a4550e8af9149739b996bf31c4b27f60f69a13c234f21c3eb357ec42df9506a",
        )
        self.assertEqual(receipt.numerator, 5_427_920_027_120_169)
        self.assertEqual(receipt.denominator, 1 << 53)
        self.assertEqual(receipt.uniform, 0.6026201789932816)

    def test_order_eos_and_resume_do_not_advance_streams(self) -> None:
        steps = range(12)
        uninterrupted = {
            branch: [
                hash_uniform(**self.key, decode_step=step)
                for step in steps
                if not (branch == "early_eos" and step > 2)
            ]
            for branch in ("full", "early_eos")
        }

        # Reverse execution order and simulate interruption after step four.
        reversed_resumed: dict[str, list[float]] = {}
        for branch in reversed(("full", "early_eos")):
            before = [
                hash_uniform(**self.key, decode_step=step)
                for step in range(5)
                if not (branch == "early_eos" and step > 2)
            ]
            after = [
                hash_uniform(**self.key, decode_step=step)
                for step in range(5, 12)
                if not (branch == "early_eos" and step > 2)
            ]
            reversed_resumed[branch] = before + after

        self.assertEqual(reversed_resumed, uninterrupted)
        # Paired branches deliberately receive the same noise at a given step.
        self.assertEqual(
            uninterrupted["full"][:3], uninterrupted["early_eos"]
        )

    def test_step_and_stream_identity_are_part_of_hash(self) -> None:
        base = hash_uniform(**self.key, decode_step=0)
        later = hash_uniform(**self.key, decode_step=1)
        other_stream = hash_uniform(
            sampling_domain_hash=self.key["sampling_domain_hash"],
            prefix_seed=self.key["prefix_seed"],
            paired_stream_id="paired-main-0008",
            decode_step=0,
        )
        self.assertNotEqual(base, later)
        self.assertNotEqual(base, other_stream)

    def test_terminal_event_resolves_without_post_eos_fixed_probes(self) -> None:
        schedule = (-1, 0, 4, 16, "terminal")
        early = resolve_probe_event_times(
            schedule, generated_token_count=9, terminal_reason="eos"
        )
        self.assertEqual(
            [(row.event_time, row.resolved_step) for row in early],
            [(-1, -1), (0, 0), (4, 4), ("terminal", 9)],
        )
        self.assertEqual(early[-1].terminal_reason, "eos")

        capped = resolve_probe_event_times(
            schedule, generated_token_count=64, terminal_reason="cap"
        )
        self.assertEqual(
            [(row.event_time, row.resolved_step) for row in capped],
            [(-1, -1), (0, 0), (4, 4), (16, 16), ("terminal", 64)],
        )


@unittest.skipIf(torch is None, "synthetic model gates require PyTorch")
class TorchRuntimeTests(unittest.TestCase):
    class FakeDynamicCache:
        def __init__(self, legacy: object) -> None:
            self.legacy = legacy

        def to_legacy_cache(self) -> object:
            return self.legacy

        @classmethod
        def from_legacy_cache(cls, legacy: object) -> "TorchRuntimeTests.FakeDynamicCache":
            return cls(legacy)

    class TinyTupleBlock(torch.nn.Module if torch is not None else object):
        def __init__(self, width: int, offset: float) -> None:
            super().__init__()
            self.register_buffer(
                "offset", torch.full((width,), float(offset), dtype=torch.float32)
            )

        def forward(self, hidden: object) -> tuple[object]:
            return (hidden + self.offset.view(1, 1, -1),)

    class TinyCachedLM(torch.nn.Module if torch is not None else object):
        def __init__(self) -> None:
            super().__init__()
            width = 4
            vocab = 7
            self.embedding = torch.nn.Embedding(vocab, width)
            self.layers = torch.nn.ModuleList(
                [
                    TorchRuntimeTests.TinyTupleBlock(width, 0.03),
                    TorchRuntimeTests.TinyTupleBlock(width, -0.02),
                    TorchRuntimeTests.TinyTupleBlock(width, 0.01),
                ]
            )
            self.head = torch.nn.Linear(width, vocab, bias=False)
            with torch.no_grad():
                self.embedding.weight.copy_(
                    torch.arange(vocab * width, dtype=torch.float32).reshape(vocab, width)
                    / 17.0
                )
                self.head.weight.copy_(
                    torch.arange(vocab * width, dtype=torch.float32).reshape(vocab, width)
                    / 23.0
                )

        def forward(
            self, token_ids: object, past: object | None = None
        ) -> tuple[object, object]:
            hidden = self.embedding(token_ids)
            if past:
                hidden = hidden + past[-1][0][:, -1:, :] * 0.01
            for layer in self.layers:
                hidden = layer(hidden)[0]
            logits = self.head(hidden[:, -1, :])
            current = hidden.detach().clone()
            new_cache = tuple(past or ()) + ((current, current * 2),)
            return logits, new_cache

    def test_inverse_cdf_matches_manual_and_replays(self) -> None:
        logits = torch.tensor([-1.5, 0.2, 1.1, -0.1], dtype=torch.float32)
        kwargs = {
            "sampling_domain_hash": "a" * 64,
            "prefix_seed": 91,
            "paired_stream_id": "paired-fixture",
            "decode_step": 3,
            "temperature": 0.5,
            "top_p": 1.0,
            "top_k": None,
        }
        decision = inverse_cdf_sample(logits, **kwargs)
        probabilities = torch.softmax(logits.double() / 0.5, dim=0)
        uniform = decision.uniform_receipt.uniform
        expected = next(
            index
            for index, value in enumerate(torch.cumsum(probabilities, dim=0).tolist())
            if value > uniform
        )
        self.assertEqual(decision.token_id, expected)
        self.assertEqual(decision, inverse_cdf_sample(logits, **kwargs))

    def test_sampling_is_branch_order_and_resume_invariant(self) -> None:
        branch_logits = {
            "supp": torch.tensor([0.1, 0.5, -0.3, 0.2]),
            "amp": torch.tensor([-0.4, 0.2, 0.7, 0.1]),
            "eos": torch.tensor([0.2, 0.1, 0.4, -0.2]),
        }

        def execute(order: tuple[str, ...], ranges: tuple[range, ...]) -> dict[str, list[int]]:
            rows = {name: [] for name in branch_logits}
            for decode_range in ranges:
                for branch in order:
                    for step in decode_range:
                        if branch == "eos" and step > 1:
                            continue
                        rows[branch].append(
                            inverse_cdf_sample(
                                branch_logits[branch],
                                sampling_domain_hash="b" * 64,
                                prefix_seed=101,
                                paired_stream_id="shared-paired-noise",
                                decode_step=step,
                                temperature=0.5,
                            ).token_id
                        )
            return rows

        reference = execute(("supp", "amp", "eos"), (range(0, 8),))
        resumed = execute(("eos", "amp", "supp"), (range(0, 3), range(3, 8)))
        self.assertEqual(reference, resumed)

    def test_legacy_and_dynamic_cache_clones_are_disjoint_and_hash_stable(self) -> None:
        legacy = (
            (
                torch.arange(12, dtype=torch.float32).reshape(1, 1, 3, 4),
                torch.arange(12, 24, dtype=torch.float32).reshape(1, 1, 3, 4),
            ),
        )
        source_hash = cache_tensor_sha256(legacy)
        cloned = clone_kv_cache(legacy)
        self.assertEqual(cache_tensor_sha256(cloned), source_hash)
        self.assertNotEqual(cloned[0][0].data_ptr(), legacy[0][0].data_ptr())
        cloned[0][0].add_(1)
        self.assertEqual(cache_tensor_sha256(legacy), source_hash)
        self.assertNotEqual(cache_tensor_sha256(cloned), source_hash)

        dynamic = self.FakeDynamicCache(legacy)
        dynamic_clone = clone_kv_cache(dynamic)
        self.assertIsInstance(dynamic_clone, self.FakeDynamicCache)
        self.assertEqual(cache_tensor_sha256(dynamic_clone), source_hash)
        self.assertNotEqual(
            dynamic_clone.legacy[0][0].data_ptr(), legacy[0][0].data_ptr()
        )

    def test_first_affected_forward_has_zero_pre_event_effect(self) -> None:
        model = self.TinyCachedLM().eval()
        with torch.no_grad():
            pre_logits, prefix_cache = model(torch.tensor([[1]]))
        prefix_hash = cache_tensor_sha256(prefix_cache)

        never_cache = clone_kv_cache(prefix_cache)
        active_cache = clone_kv_cache(prefix_cache)
        with torch.no_grad():
            never_logits, _ = model(torch.tensor([[2]]), never_cache)

        switch = Layer50SwitchHook(
            torch.tensor([0.4, -0.3, 0.2, 0.1]), capture_to_cpu=True
        ).register(model.layers[1])
        switch.arm(torch.tensor([True]), forward_id="event0")
        with torch.no_grad():
            active_logits, _ = model(torch.tensor([[2]]), active_cache)
        capture = switch.pop_capture(expected_forward_id="event0")
        switch.remove()
        switch.validate_complete(expected_calls=1)

        # The event hook did not touch or recompute the pre-event cache/state.
        self.assertEqual(cache_tensor_sha256(prefix_cache), prefix_hash)
        self.assertEqual(cache_tensor_sha256(never_cache), prefix_hash)
        self.assertEqual(cache_tensor_sha256(active_cache), prefix_hash)
        self.assertTrue(torch.isfinite(pre_logits).all())

        # h50_pre is the clean current-token state; h50_post is its exact edit.
        observed = capture.post - capture.pre
        expected = torch.tensor([0.4, -0.3, 0.2, 0.1]).view(1, 1, -1)
        self.assertTrue(torch.allclose(observed, expected, rtol=0, atol=1e-7))
        self.assertFalse(torch.equal(active_logits, never_logits))

        # Once removed, the identical event input/cache returns to the never arm.
        with torch.no_grad():
            after_removal, _ = model(torch.tensor([[2]]), clone_kv_cache(prefix_cache))
        self.assertTrue(torch.equal(after_removal, never_logits))

    def test_masks_sham_and_removal_are_exact(self) -> None:
        block = self.TinyTupleBlock(width=4, offset=0.0).eval()
        hidden = torch.arange(12, dtype=torch.float32).reshape(1, 3, 4)
        baseline = block(hidden)[0]

        sham = Layer50SwitchHook(torch.zeros(4)).register(block)
        sham.arm([1, 1, 1], forward_id="sham-prefill")
        sham_output = block(hidden)[0]
        sham_capture = sham.pop_capture(expected_forward_id="sham-prefill")
        sham.remove()
        sham.validate_complete(expected_calls=1)
        self.assertTrue(torch.equal(sham_output, baseline))
        self.assertTrue(torch.equal(sham_capture.pre, sham_capture.post))
        self.assertEqual(sham.telemetry()["selected_position_count"], 3)

        active = Layer50SwitchHook(torch.ones(4)).register(block)
        active.arm(
            [0, 1, 0], forward_id="masked-incremental", event_time="terminal"
        )
        active_output = block(hidden)[0]
        capture = active.pop_capture(expected_forward_id="masked-incremental")
        active.remove()
        active.validate_complete(expected_calls=1)
        self.assertEqual(active.telemetry()["call_receipts"][0]["event_time"], "terminal")
        delta = active_output - baseline
        self.assertTrue(torch.equal(delta[:, 0], torch.zeros((1, 4))))
        self.assertTrue(torch.equal(delta[:, 1], torch.ones((1, 4))))
        self.assertTrue(torch.equal(delta[:, 2], torch.zeros((1, 4))))
        self.assertTrue(torch.equal(capture.position_mask, torch.tensor([[False, True, False]])))
        self.assertTrue(torch.equal(block(hidden)[0], baseline))

    def test_hook_fails_closed_on_unarmed_or_bad_masks(self) -> None:
        block = self.TinyTupleBlock(width=4, offset=0.0).eval()
        hidden = torch.zeros((1, 2, 4))
        hook = Layer50SwitchHook(torch.ones(4)).register(block)
        with self.assertRaises(RuntimeContractError):
            block(hidden)
        # The unarmed failure does not create a pending mask, so removal is safe.
        hook.remove()
        hook.validate_complete(expected_calls=0)

        mismatch = Layer50SwitchHook(torch.ones(4)).register(block)
        mismatch.arm([1], forward_id="wrong-mask")
        with self.assertRaises(RuntimeContractError):
            block(hidden)
        # The failed forward consumed its identity and cannot be retried silently.
        mismatch.remove()
        mismatch.validate_complete(expected_calls=0)

    def test_residual_extraction_has_explicit_shapes_and_copies(self) -> None:
        hidden = torch.arange(2 * 3 * 4, dtype=torch.float32).reshape(2, 3, 4)
        output = (hidden, "aux")
        last = extract_residual_positions(output, -1)
        selected = extract_residual_positions(output, [0, 2], batch_index=1)
        self.assertEqual(tuple(last.shape), (2, 4))
        self.assertEqual(tuple(selected.shape), (2, 4))
        self.assertTrue(torch.equal(last, hidden[:, -1, :]))
        self.assertTrue(torch.equal(selected, hidden[1, [0, 2], :]))
        hidden.add_(100)
        self.assertFalse(torch.equal(last, hidden[:, -1, :]))


if __name__ == "__main__":
    unittest.main()
