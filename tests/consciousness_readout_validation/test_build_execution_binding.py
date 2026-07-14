from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from experiments.consciousness_readout_validation import protocol, runtime
from experiments.consciousness_readout_validation.build_execution_binding import (
    build_binding_payload,
    inventory_snapshot,
    resolve_declared_binding_path,
)


class ExecutionBindingBuilderTests(unittest.TestCase):
    def test_snapshot_inventory_is_sorted_and_tokenizer_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tokenizer.json").write_text("{}", encoding="utf-8")
            (root / "config.json").write_text("{}", encoding="utf-8")
            rows, inventory, tokenizer_inventory = inventory_snapshot(root)
        self.assertEqual([row["path"] for row in rows], ["config.json", "tokenizer.json"])
        self.assertEqual(inventory, protocol.canonical_sha256(rows))
        self.assertEqual(
            tokenizer_inventory,
            protocol.canonical_sha256([row for row in rows if row["path"] == "tokenizer.json"]),
        )

    def test_snapshot_inventory_rejects_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "real.json").write_text("{}", encoding="utf-8")
            os.symlink(root / "real.json", root / "tokenizer.json")
            with self.assertRaises(runtime.PilotRuntimeError):
                inventory_snapshot(root)

    def test_binding_payload_is_self_hashed_and_model_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "model"
            model.mkdir()
            sae = root / "sae.pt"
            sae_readme = root / "README.md"
            sae_config = root / "sae-config.yaml"
            lens = root / "lens.pt"
            lens_config = root / "config.yaml"
            sae.write_bytes(b"sae")
            sae_readme.write_bytes(b"readme")
            sae_config.write_bytes(b"sae config")
            lens.write_bytes(b"lens")
            lens_config.write_bytes(b"config")
            rows = [{"path": "tokenizer.json", "sha256": "1" * 64}]
            binding = build_binding_payload(
                plan_manifest_sha256="2" * 64,
                plan_validation_receipt={"plan_manifest_sha256": "2" * 64},
                volume_id="volume",
                model_snapshot=model,
                model_files=rows,
                model_file_inventory_sha256=protocol.canonical_sha256(rows),
                tokenizer_inventory_sha256="3" * 64,
                sae_path=sae,
                sae_readme_path=sae_readme,
                sae_config_path=sae_config,
                j_lens_path=lens,
                j_lens_config_path=lens_config,
                tokenizer_audit_receipt_sha256="4" * 64,
            )
        for dotted_path in protocol.REQUIRED_EXECUTION_BINDING_PATHS:
            self.assertIsNotNone(resolve_declared_binding_path(binding, dotted_path))
        digest = binding.pop("execution_binding_canonical_sha256")
        self.assertEqual(digest, protocol.canonical_sha256(binding))
        self.assertFalse(binding["model_weights_loaded"])
        self.assertEqual(binding["model_forward_count"], 0)
        self.assertEqual(binding["container_image"], protocol.CONTAINER_IMAGE_SPEC)
        self.assertEqual(
            binding["artifacts"]["j_lens"]["config_sha256"],
            protocol.J_LENS_SPEC["release_config"]["sha256"],
        )
        self.assertEqual(
            binding["artifacts"]["sae"]["readme_sha256"],
            protocol.SAE_SPEC["sidecars"]["readme"]["sha256"],
        )
        self.assertEqual(
            binding["artifacts"]["sae"]["config_sha256"],
            protocol.SAE_SPEC["sidecars"]["config"]["sha256"],
        )
        serialized = json.dumps(binding)
        self.assertNotIn("target_prompt\"", serialized)


if __name__ == "__main__":
    unittest.main()
