from __future__ import annotations

import unittest

from experiments.consciousness_sae_changepoint import artifact_audit

try:
    import torch
except ModuleNotFoundError:  # Lightweight local verification environment.
    torch = None


@unittest.skipUnless(torch is not None, "artifact tensor audit requires PyTorch")
class LmHeadAuditTests(unittest.TestCase):
    def test_valid_bf16_head_is_receipted(self) -> None:
        tensor = torch.arange(12, dtype=torch.bfloat16).reshape(3, 4)
        receipt = artifact_audit._validate_lm_head_tensor(
            torch, tensor, expected_rows=3, expected_width=4
        )
        self.assertEqual(receipt["shape"], [3, 4])
        self.assertEqual(receipt["dtype"], "torch.bfloat16")
        self.assertTrue(receipt["finite"])
        self.assertEqual(len(receipt["tensor_sha256"]), 64)

    def test_wrong_shape_fails(self) -> None:
        with self.assertRaises(artifact_audit.ArtifactAuditError):
            artifact_audit._validate_lm_head_tensor(
                torch,
                torch.zeros((2, 4), dtype=torch.bfloat16),
                expected_rows=3,
                expected_width=4,
            )

    def test_nonfinite_head_fails(self) -> None:
        tensor = torch.zeros((3, 4), dtype=torch.bfloat16)
        tensor[1, 2] = float("nan")
        with self.assertRaises(artifact_audit.ArtifactAuditError):
            artifact_audit._validate_lm_head_tensor(
                torch, tensor, expected_rows=3, expected_width=4
            )


if __name__ == "__main__":
    unittest.main()
