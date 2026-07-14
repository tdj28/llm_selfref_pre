from __future__ import annotations

import unittest
from unittest import mock

from experiments.consciousness_sae_realization_validation import runtime


class _FakeTensor:
    def __init__(self, values: tuple[float, ...], device: str) -> None:
        self.values = values
        self.device = device
        self.to_calls: list[str] = []

    def to(self, *, device: str) -> "_FakeTensor":
        self.to_calls.append(device)
        return _FakeTensor(self.values, device)


class MetricPairContractTests(unittest.TestCase):
    def test_backend_exposes_the_exact_successor_call_surface(self) -> None:
        for name in (
            "capture_layer50_all_tokens",
            "close",
            "j_matrix",
            "prepare_arc",
            "runtime_metadata",
            "selected_logits_from_state",
            "start_runtime_interval",
            "transport_realized",
        ):
            self.assertTrue(callable(getattr(runtime.V2Backend, name, None)), name)

    def test_metric_pair_moves_only_right_operand_to_left_device(self) -> None:
        left = _FakeTensor((1.0, 2.0), "cuda:0")
        right = _FakeTensor((3.0, 4.0), "cpu")

        observed_left, observed_right = runtime._metric_pair(left, right)

        self.assertIs(observed_left, left)
        self.assertEqual(observed_right.device, left.device)
        self.assertEqual(observed_right.values, right.values)
        self.assertEqual(left.to_calls, [])
        self.assertEqual(right.to_calls, ["cuda:0"])

    def test_metric_pair_does_not_copy_already_colocated_operands(self) -> None:
        left = _FakeTensor((1.0,), "cpu")
        right = _FakeTensor((2.0,), "cpu")

        observed_left, observed_right = runtime._metric_pair(left, right)

        self.assertIs(observed_left, left)
        self.assertIs(observed_right, right)
        self.assertEqual(left.to_calls, [])
        self.assertEqual(right.to_calls, [])

    def test_public_metric_wrapper_passes_colocated_values_to_backend(self) -> None:
        left = _FakeTensor((1.0, 2.0), "cuda:0")
        right = _FakeTensor((3.0, 4.0), "cpu")

        def assert_colocated(observed_left: _FakeTensor, observed_right: _FakeTensor) -> float:
            self.assertEqual(observed_left.device, "cuda:0")
            self.assertEqual(observed_right.device, "cuda:0")
            self.assertEqual(observed_right.values, right.values)
            return 0.25

        with mock.patch.object(
            runtime,
            "_cosine_similarity",
            side_effect=assert_colocated,
        ):
            self.assertEqual(runtime.cosine(left, right), 0.25)

    def test_real_cpu_tensors_remain_colocated_when_torch_is_available(self) -> None:
        try:
            import torch
        except ImportError:
            self.skipTest("PyTorch is not installed in the CPU test environment")

        left = torch.tensor([1.0, 2.0])
        right = torch.tensor([3.0, 4.0])
        observed_left, observed_right = runtime._metric_pair(left, right)
        self.assertIs(observed_left, left)
        self.assertIs(observed_right, right)
        self.assertEqual(observed_left.device, observed_right.device)


if __name__ == "__main__":
    unittest.main()
