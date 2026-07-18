from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.consciousness_readout_validation import paths, protocol
from experiments.consciousness_readout_validation.build_plan import (
    PLAN_MANIFEST_FILENAME,
    PLAN_PAYLOAD_FILES,
    build_manifest,
    build_plan,
)
from experiments.consciousness_readout_validation.inventory import BOUND_REPOSITORY_PATHS
from experiments.consciousness_readout_validation.protocol import canonical_json_bytes
from experiments.consciousness_readout_validation.validate_plan import (
    InvalidPilotPlan,
    validate_plan,
)


class MachinePlanTests(unittest.TestCase):
    def _build(self, root: Path, name: str) -> Path:
        output = root / name
        with patch.object(paths, "DATA_ROOT", root):
            build_plan(output)
            validate_plan(output)
        return output

    def test_two_builds_are_byte_identical_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self._build(root, "first")
            second = self._build(root, "second")
            self.assertEqual(
                {path.name: path.read_bytes() for path in first.iterdir()},
                {path.name: path.read_bytes() for path in second.iterdir()},
            )
            with patch.object(paths, "DATA_ROOT", root):
                receipt = validate_plan(first)
            self.assertEqual(receipt["status"], "valid_target_blind_pilot_plan_execution_bindings_unresolved")
            self.assertEqual(len(receipt["canonical_payload_sha256"]), 64)
            self.assertEqual(len(receipt["plan_manifest_sha256"]), 64)
            self.assertEqual(len(receipt["manifest_file_sha256"]), 64)
            self.assertEqual(
                len(
                    {
                        receipt["canonical_payload_sha256"],
                        receipt["plan_manifest_sha256"],
                        receipt["manifest_file_sha256"],
                    }
                ),
                3,
            )

    def test_tamper_is_rejected_even_if_attacker_rehashes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = self._build(root, "tampered")
            neutral_path = plan / "neutral_prompts.jsonl"
            lines = neutral_path.read_text(encoding="utf-8").splitlines()
            first = json.loads(lines[0])
            first["question"] = "Tampered text?"
            lines[0] = canonical_json_bytes(first).decode("utf-8")
            neutral_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            payloads = {filename: (plan / filename).read_bytes() for filename in PLAN_PAYLOAD_FILES}
            forged_manifest = build_manifest(payloads)
            (plan / PLAN_MANIFEST_FILENAME).write_bytes(
                canonical_json_bytes(forged_manifest) + b"\n"
            )
            with patch.object(paths, "DATA_ROOT", root):
                with self.assertRaisesRegex(InvalidPilotPlan, "reconstruction mismatch"):
                    validate_plan(plan)

    def test_unexpected_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = self._build(root, "unexpected")
            (plan / "extra.json").write_text("{}\n", encoding="utf-8")
            with patch.object(paths, "DATA_ROOT", root):
                with self.assertRaisesRegex(InvalidPilotPlan, "file set mismatch"):
                    validate_plan(plan)

    def test_source_inventory_binds_new_sources_tests_fixtures_and_docs(self) -> None:
        required = {
            "experiments/consciousness_readout_validation/fixtures.py",
            "experiments/consciousness_readout_validation/analysis.py",
            "experiments/consciousness_readout_validation/analyze_pilot.py",
            "experiments/consciousness_readout_validation/audit_pilot.py",
            "experiments/consciousness_readout_validation/build_execution_binding.py",
            "experiments/consciousness_readout_validation/guest_attestation.py",
            "experiments/consciousness_readout_validation/gpu_runner.py",
            "experiments/consciousness_readout_validation/requirements-runpod-b200.txt",
            "experiments/consciousness_readout_validation/run_guest_preflight.sh",
            "experiments/consciousness_readout_validation/run_pilot_runpod.sh",
            "experiments/consciousness_readout_validation/runpod_lifecycle.py",
            "experiments/consciousness_readout_validation/runtime.py",
            "experiments/consciousness_readout_validation/stage_public_artifacts.py",
            "tests/consciousness_readout_validation/test_analysis.py",
            "tests/consciousness_readout_validation/test_analyze_pilot.py",
            "tests/consciousness_readout_validation/test_audit_pilot.py",
            "tests/consciousness_readout_validation/test_build_execution_binding.py",
            "tests/consciousness_readout_validation/test_guest_attestation.py",
            "tests/consciousness_readout_validation/test_guest_preflight_wrapper.py",
            "tests/consciousness_readout_validation/test_gpu_runner.py",
            "tests/consciousness_readout_validation/test_runpod_lifecycle.py",
            "tests/consciousness_readout_validation/test_runtime.py",
            "tests/consciousness_readout_validation/test_stage_public_artifacts.py",
            "docs/consciousness_readout_validation/PROTOCOL.md",
            "docs/consciousness_sae_switch_arc/PRO_REVIEW_RECEIPT.json",
            "docs/consciousness_sae_switch_arc/PRO_REVIEW_ADJUDICATION.md",
            "data/consciousness_readout_validation/README.md",
        }
        self.assertTrue(required <= set(BOUND_REPOSITORY_PATHS))
        self.assertFalse(
            any("consciousness_sae_changepoint" in path for path in BOUND_REPOSITORY_PATHS)
        )

    def test_plan_contracts_are_explicitly_unresolved_and_result_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = self._build(root, "contracts")
            artifacts = json.loads((plan / "artifact_bindings.json").read_bytes())
            tokens = json.loads((plan / "token_metadata.json").read_bytes())
            allowlist = json.loads((plan / "input_allowlist.json").read_bytes())
            self.assertEqual(
                artifacts["binding_status"],
                "unresolved_plan_only_execution_prohibited",
            )
            self.assertEqual(
                artifacts["container_image"],
                protocol.CONTAINER_IMAGE_SPEC,
            )
            self.assertEqual(
                artifacts["artifacts"]["j_lens"]["release_config"]["sha256"],
                "d4784fe625f58f2ae90318d45b9c2355f749c334a97936a04f749423992a8eb5",
            )
            self.assertIn(
                "artifacts.j_lens.config_sha256",
                artifacts["required_execution_receipt_fields"],
            )
            self.assertIn(
                "artifacts.sae.readme_sha256",
                artifacts["required_execution_receipt_fields"],
            )
            self.assertIn(
                "artifacts.sae.config_sha256",
                artifacts["required_execution_receipt_fields"],
            )
            self.assertEqual(
                tokens["binding_status"],
                "tokenizer_audit_required_before_any_forward",
            )
            self.assertFalse(allowlist["prior_outcome_inputs"])
            self.assertFalse(allowlist["target_prompt_inputs"])
            self.assertFalse(allowlist["target_outcome_inputs"])


if __name__ == "__main__":
    unittest.main()
