from __future__ import annotations

import copy
import hashlib
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments.consciousness_readout_validation import audit_pilot, inventory, protocol
from tests.consciousness_readout_validation.test_analysis import (
    TEST_G1_TOKEN_IDS,
    TEST_PLAN_MANIFEST_SHA256,
    g1_rows,
    tokenizer_audit_receipt,
    vector_inventory_receipt,
)


def _reseal(value: dict[str, object], field: str = "receipt_sha256") -> None:
    value.pop(field, None)
    value[field] = protocol.canonical_sha256(value)


def _envelope_g1(rows: list[dict[str, object]], run_id: str = "synthetic") -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for offset, measurement in enumerate(rows):
        key = [measurement["layer"], measurement["synthetic_residual_id"]]
        task_id = protocol.stable_id(
            "measurement", {"measurement_kind": "g1", "key": key}
        )
        original = {**measurement, "task_id": task_id}
        row_id = protocol.canonical_sha256(
            {
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "parts": (
                    "G1",
                    run_id,
                    "g1_rows.jsonl",
                    offset,
                    protocol.canonical_sha256(original),
                ),
            }
        )[:32]
        result.append(
            {
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "plan_manifest_sha256": TEST_PLAN_MANIFEST_SHA256,
                "run_id": run_id,
                **original,
                "row_id": row_id,
            }
        )
    return result


def _runtime_metadata(phase: str, *, forwards: int) -> dict[str, object]:
    timestamp = "2026-07-13T12:00:00Z" if forwards else None
    core: dict[str, object] = {
        "schema_version": 1,
        "status": "pass",
        "metadata_kind": "gpu_phase_runtime_v1",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "phase": phase,
        "run_id": "synthetic",
        "plan_manifest_sha256": TEST_PLAN_MANIFEST_SHA256,
        "execution_binding_canonical_sha256": "b" * 64,
        "tokenizer_audit_receipt_sha256": "d" * 64,
        "runtime_adapter": "gpu_phase_adapter_v1",
        "hook_contract": audit_pilot.AUDITED_HOOK_CONTRACT,
        "container_image": protocol.CONTAINER_IMAGE_SPEC,
        "model": protocol.MODEL_SPEC,
        "sae": protocol.SAE_SPEC,
        "j_lens": protocol.J_LENS_SPEC,
        "hardware": {
            "cuda_device_count": 1,
            "gpu_name": "synthetic",
            "gpu_total_memory_bytes": 160 * 1024**3,
            "cuda_runtime_version": "12.8",
            "cudnn_version": 90000,
        },
        "software": {
            "python": "3.11.9",
            "python_implementation": "CPython",
            "torch": "2.8.0",
            "accelerate": "1.12.0",
            "huggingface_hub": "0.36.0",
            "numpy": "2.2.6",
            "safetensors": "0.6.2",
            "transformers": "4.57.6",
        },
        "determinism": {
            "seed": int(protocol.PILOT_RANDOM_SEED % (2**63 - 1)),
            "cublas_workspace_config": ":4096:8",
            "deterministic_algorithms": True,
            "cuda_matmul_tf32": False,
            "cudnn_tf32": False,
            "flash_sdp_enabled": False,
            "mem_efficient_sdp_enabled": False,
            "math_sdp_enabled": True,
        },
        "model_weights_loaded": True,
        "model_forward_count": forwards,
        "first_model_forward_at_utc": timestamp,
        "last_model_forward_at_utc": timestamp,
        "prior_outcome_inputs": [],
        "target_prompt_inputs": [],
        "target_outcome_inputs": [],
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


class IndependentStructuralAuditTests(unittest.TestCase):
    def test_independent_literal_source_inventory_exactly_matches_builder_inventory(self) -> None:
        self.assertEqual(
            inventory.BOUND_REPOSITORY_PATHS,
            audit_pilot.BOUND_REPOSITORY_PATHS,
        )

    """Synthetic-only adversarial checks for the independent receipt producer."""

    def test_auditor_has_no_runtime_or_prior_study_dependency(self) -> None:
        source = Path(audit_pilot.__file__).read_text(encoding="utf-8")
        self.assertNotIn("from . import runtime", source)
        self.assertNotIn("validate_plan.validate_plan", source)
        for marker in protocol.public_input_allowlist()["forbidden_path_markers"]:
            self.assertNotIn(f"import {marker}", source)

    def test_hook_and_execution_path_contracts_are_independently_frozen(self) -> None:
        self.assertEqual(
            protocol.canonical_sha256(audit_pilot.AUDITED_HOOK_CONTRACT),
            protocol.canonical_sha256(protocol.HOOK_CONTRACT),
        )
        self.assertEqual(
            audit_pilot.AUDITED_REQUIRED_EXECUTION_BINDING_PATHS,
            protocol.REQUIRED_EXECUTION_BINDING_PATHS,
        )
        self.assertEqual(
            audit_pilot.EXPECTED_J_LENS_CONFIG_SHA256,
            protocol.J_LENS_SPEC["release_config"]["sha256"],
        )
        self.assertEqual(
            audit_pilot.EXPECTED_SAE_README_SHA256,
            protocol.SAE_SPEC["sidecars"]["readme"]["sha256"],
        )
        self.assertEqual(
            audit_pilot.EXPECTED_SAE_CONFIG_SHA256,
            protocol.SAE_SPEC["sidecars"]["config"]["sha256"],
        )
        self.assertEqual(
            protocol.canonical_sha256(audit_pilot.AUDITED_GATE_CONSEQUENCE_POLICY),
            protocol.canonical_sha256(protocol.GATE_CONSEQUENCE_POLICY),
        )

    def test_independent_sae_layout_rejects_extra_key_and_shape_tamper(self) -> None:
        class Shaped:
            def __init__(self, shape: tuple[int, ...]) -> None:
                self.shape = shape

        shapes = audit_pilot.AUDITED_HOOK_CONTRACT["sae"]
        state = {
            "module.encoder_linear.weight": Shaped(tuple(shapes["encoder_weight_shape"])),
            "module.encoder_linear.bias": Shaped(tuple(shapes["encoder_bias_shape"])),
            "module.decoder_linear.weight": Shaped(tuple(shapes["decoder_weight_shape"])),
            "module.decoder_linear.bias": Shaped(tuple(shapes["decoder_bias_shape"])),
        }
        resolved = audit_pilot._resolve_sae_state_independent(state)
        self.assertEqual(set(resolved), {
            "encoder_linear.weight",
            "encoder_linear.bias",
            "decoder_linear.weight",
            "decoder_linear.bias",
        })
        extra = {**state, "unexpected": Shaped((1,))}
        with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "exactly the four"):
            audit_pilot._resolve_sae_state_independent(extra)
        bad_shape = dict(state)
        bad_shape["module.decoder_linear.bias"] = Shaped((8191,))
        with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "shape differs"):
            audit_pilot._resolve_sae_state_independent(bad_shape)

    def test_execution_audit_rehashes_every_sae_and_jlens_sidecar(self) -> None:
        repo = Path(audit_pilot.__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "external"
            public = (
                root
                / protocol.STUDY_SLUG
                / protocol.STUDY_ID
                / "public_artifacts"
            )
            model = public / "model"
            sae_dir = public / "sae"
            lens_dir = public / "jlens"
            model.mkdir(parents=True)
            sae_dir.mkdir()
            lens_dir.mkdir()
            tokenizer = model / "tokenizer.json"
            sae = sae_dir / "sae.pt"
            sae_readme = sae_dir / "README.md"
            sae_config = sae_dir / "config.yaml"
            lens = lens_dir / "lens.pt"
            lens_config = lens_dir / "config.yaml"
            tokenizer.write_bytes(b"tokenizer")
            sae.write_bytes(b"sae")
            sae_readme.write_bytes(b"sae readme")
            sae_config.write_bytes(b"sae config")
            lens.write_bytes(b"lens")
            lens_config.write_bytes(b"lens config")
            digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            sae_hash = digest(sae)
            sae_readme_hash = digest(sae_readme)
            sae_config_hash = digest(sae_config)
            lens_hash = digest(lens)
            lens_config_hash = digest(lens_config)
            model_rows = [{"path": "tokenizer.json", "sha256": digest(tokenizer)}]
            model_inventory = protocol.canonical_sha256(model_rows)
            sentinel = {
                "study_slug": protocol.STUDY_SLUG,
                "study_id": protocol.STUDY_ID,
                "volume_id": "synthetic-volume",
            }
            (root / audit_pilot.VOLUME_SENTINEL).write_bytes(
                protocol.canonical_json_bytes(sentinel) + b"\n"
            )
            sae_sidecars = {
                "readme": {
                    "filename": audit_pilot.EXPECTED_SAE_README_FILENAME,
                    "sha256": sae_readme_hash,
                },
                "config": {
                    "filename": audit_pilot.EXPECTED_SAE_CONFIG_FILENAME,
                    "sha256": sae_config_hash,
                },
            }
            lens_release = {
                **protocol.J_LENS_SPEC["release_config"],
                "sha256": lens_config_hash,
            }
            core = {
                "schema_version": 1,
                "status": "pass",
                "binding_kind": "target_blind_pilot_execution_binding_v1",
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "plan_manifest_sha256": TEST_PLAN_MANIFEST_SHA256,
                "plan_validation_receipt_sha256": "a" * 64,
                "resolved_external_root_id": "synthetic-volume",
                "container_image": protocol.CONTAINER_IMAGE_SPEC,
                "runtime_adapter": "gpu_phase_adapter_v1",
                "runtime_adapter_source_sha256": digest(
                    repo / "experiments/consciousness_readout_validation/gpu_runner.py"
                ),
                "tokenizer_content_inventory_sha256": model_inventory,
                "tokenizer_audit_receipt_sha256": "d" * 64,
                "artifacts": {
                    "model_snapshot": {
                        "path": str(model),
                        "repository": protocol.MODEL_SPEC["repository"],
                        "revision": protocol.MODEL_SPEC["revision"],
                        "files": model_rows,
                        "file_inventory_sha256": model_inventory,
                    },
                    "sae": {
                        "path": str(sae),
                        "readme_path": str(sae_readme),
                        "config_path": str(sae_config),
                        "repository": protocol.SAE_SPEC["repository"],
                        "revision": protocol.SAE_SPEC["revision"],
                        "filename": protocol.SAE_SPEC["filename"],
                        "sha256": sae_hash,
                        "readme_filename": audit_pilot.EXPECTED_SAE_README_FILENAME,
                        "readme_sha256": sae_readme_hash,
                        "config_filename": audit_pilot.EXPECTED_SAE_CONFIG_FILENAME,
                        "config_sha256": sae_config_hash,
                    },
                    "j_lens": {
                        "path": str(lens),
                        "config_path": str(lens_config),
                        "repository": protocol.J_LENS_SPEC["repository"],
                        "revision": protocol.J_LENS_SPEC["revision"],
                        "filename": protocol.J_LENS_SPEC["filename"],
                        "sha256": lens_hash,
                        "config_filename": audit_pilot.EXPECTED_J_LENS_CONFIG_FILENAME,
                        "config_sha256": lens_config_hash,
                    },
                },
                "model_weights_loaded": False,
                "model_forward_count": 0,
                "prior_outcome_inputs": [],
                "target_prompt_inputs": [],
                "target_outcome_inputs": [],
            }
            binding = {
                **core,
                "execution_binding_canonical_sha256": protocol.canonical_sha256(core),
            }
            binding_path = root / "binding.json"
            binding_path.write_bytes(protocol.canonical_json_bytes(binding) + b"\n")
            with mock.patch.dict(
                protocol.SAE_SPEC,
                {"sha256": sae_hash, "sidecars": sae_sidecars},
            ), mock.patch.dict(
                protocol.J_LENS_SPEC,
                {"sha256": lens_hash, "release_config": lens_release},
            ), mock.patch.object(
                audit_pilot, "EXPECTED_SAE_README_SHA256", sae_readme_hash
            ), mock.patch.object(
                audit_pilot, "EXPECTED_SAE_CONFIG_SHA256", sae_config_hash
            ), mock.patch.object(
                audit_pilot, "EXPECTED_J_LENS_CONFIG_SHA256", lens_config_hash
            ):
                _binding, resolved = audit_pilot._validate_execution_and_artifacts(
                    binding_path,
                    plan_manifest_sha256=TEST_PLAN_MANIFEST_SHA256,
                    artifact_root=root,
                    volume_id="synthetic-volume",
                    repo_root=repo,
                )
                self.assertEqual(resolved["sae_readme"], sae_readme.resolve())
                self.assertEqual(resolved["sae_config"], sae_config.resolve())
                self.assertEqual(resolved["j_lens_config"], lens_config.resolve())
                for path in (sae_readme, sae_config, lens_config):
                    original = path.read_bytes()
                    path.write_bytes(b"tampered")
                    with self.assertRaisesRegex(
                        audit_pilot.StructuralAuditError, "bytes differ"
                    ):
                        audit_pilot._validate_execution_and_artifacts(
                            binding_path,
                            plan_manifest_sha256=TEST_PLAN_MANIFEST_SHA256,
                            artifact_root=root,
                            volume_id="synthetic-volume",
                            repo_root=repo,
                        )
                    path.write_bytes(original)

    def test_complete_tokenizer_receipt_and_each_coverage_tamper(self) -> None:
        receipt = tokenizer_audit_receipt()
        result = audit_pilot.validate_tokenizer_receipt(
            receipt,
            plan_manifest_sha256=TEST_PLAN_MANIFEST_SHA256,
            tokenizer_inventory_sha256="c" * 64,
        )
        self.assertEqual(result["token_ids"], TEST_G1_TOKEN_IDS)

        candidate = copy.deepcopy(receipt)
        candidate["g1"]["candidate_sequence"][0]["token_id"] += 1  # type: ignore[index]
        g1 = candidate["g1"]  # type: ignore[assignment]
        g1.pop("token_panel_canonical_sha256")  # type: ignore[union-attr]
        g1["token_panel_canonical_sha256"] = protocol.canonical_sha256(g1)  # type: ignore[index]
        _reseal(candidate)
        with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "g1_sequence"):
            audit_pilot.validate_tokenizer_receipt(
                candidate,
                plan_manifest_sha256=TEST_PLAN_MANIFEST_SHA256,
                tokenizer_inventory_sha256="c" * 64,
            )

        semantic = copy.deepcopy(receipt)
        semantic["semantic"]["contextual_boundaries"][0][  # type: ignore[index]
            "continuation_full_token_ids_sha256"
        ].pop("conscious")
        _reseal(semantic)
        with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "semantic_context"):
            audit_pilot.validate_tokenizer_receipt(
                semantic,
                plan_manifest_sha256=TEST_PLAN_MANIFEST_SHA256,
                tokenizer_inventory_sha256="c" * 64,
            )

        polarity = copy.deepcopy(receipt)
        polarity["polarity"]["contextual_boundaries"][0]["continuations"]["Yes"][  # type: ignore[index]
            "token_id"
        ] = 999
        _reseal(polarity)
        with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "polarity_context"):
            audit_pilot.validate_tokenizer_receipt(
                polarity,
                plan_manifest_sha256=TEST_PLAN_MANIFEST_SHA256,
                tokenizer_inventory_sha256="c" * 64,
            )

    def test_exact_task_fallback_row_id_schema_and_order(self) -> None:
        rows = _envelope_g1(g1_rows())
        kwargs = {
            "filename": "g1_rows.jsonl",
            "phase": "G1",
            "run_id": "synthetic",
            "plan_hash": TEST_PLAN_MANIFEST_SHA256,
            "token_ids": TEST_G1_TOKEN_IDS,
            "semantic_endpoint_ids": {},
        }
        audit_pilot._validate_measurement_rows(
            rows, global_task_ids=set(), global_row_ids=set(), **kwargs
        )
        for field, expected_code in (("task_id", "task_id"), ("row_id", "row_id")):
            tampered = copy.deepcopy(rows)
            tampered[0][field] = "tampered"
            with self.assertRaisesRegex(audit_pilot.StructuralAuditError, expected_code):
                audit_pilot._validate_measurement_rows(
                    tampered, global_task_ids=set(), global_row_ids=set(), **kwargs
                )
        reordered = copy.deepcopy(rows)
        reordered[0], reordered[1] = reordered[1], reordered[0]
        with self.assertRaises(audit_pilot.StructuralAuditError):
            audit_pilot._validate_measurement_rows(
                reordered, global_task_ids=set(), global_row_ids=set(), **kwargs
            )
        extra = copy.deepcopy(rows)
        extra[0]["unfrozen"] = True
        with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "schema"):
            audit_pilot._validate_measurement_rows(
                extra, global_task_ids=set(), global_row_ids=set(), **kwargs
            )

    def test_g1_zero_forward_is_exact_and_other_phases_require_forwards(self) -> None:
        audit_pilot._validate_runtime_metadata(
            _runtime_metadata("G1", forwards=0),
            phase="G1",
            run_id="synthetic",
            plan_hash=TEST_PLAN_MANIFEST_SHA256,
            execution_hash="b" * 64,
            tokenizer_receipt_hash="d" * 64,
        )
        audit_pilot._validate_runtime_metadata(
            _runtime_metadata("G2", forwards=1),
            phase="G2",
            run_id="synthetic",
            plan_hash=TEST_PLAN_MANIFEST_SHA256,
            execution_hash="b" * 64,
            tokenizer_receipt_hash="d" * 64,
        )
        with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "zero model forwards"):
            audit_pilot._validate_runtime_metadata(
                _runtime_metadata("G1", forwards=1),
                phase="G1",
                run_id="synthetic",
                plan_hash=TEST_PLAN_MANIFEST_SHA256,
                execution_hash="b" * 64,
                tokenizer_receipt_hash="d" * 64,
            )
        with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "at least one"):
            audit_pilot._validate_runtime_metadata(
                _runtime_metadata("G2", forwards=0),
                phase="G2",
                run_id="synthetic",
                plan_hash=TEST_PLAN_MANIFEST_SHA256,
                execution_hash="b" * 64,
                tokenizer_receipt_hash="d" * 64,
            )

    def test_runtime_metadata_canonical_json_round_trip_validates(self) -> None:
        metadata = _runtime_metadata("G2", forwards=1)
        round_tripped = json.loads(protocol.canonical_json_bytes(metadata))
        self.assertEqual(
            protocol.canonical_sha256(round_tripped["hook_contract"]),
            protocol.canonical_sha256(audit_pilot.AUDITED_HOOK_CONTRACT),
        )
        audit_pilot._validate_runtime_metadata(
            round_tripped,
            phase="G2",
            run_id="synthetic",
            plan_hash=TEST_PLAN_MANIFEST_SHA256,
            execution_hash="b" * 64,
            tokenizer_receipt_hash="d" * 64,
        )
        tampered = copy.deepcopy(round_tripped)
        tampered["hook_contract"]["j_lens"]["source_layers"][0] = 44
        with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "runtime_metadata"):
            audit_pilot._validate_runtime_metadata(
                tampered,
                phase="G2",
                run_id="synthetic",
                plan_hash=TEST_PLAN_MANIFEST_SHA256,
                execution_hash="b" * 64,
                tokenizer_receipt_hash="d" * 64,
            )

    def test_independent_plan_rebuild_detects_payload_and_source_drift(self) -> None:
        repo = Path(audit_pilot.__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            plan = Path(temporary) / "plan"
            plan.mkdir()
            payloads = audit_pilot._expected_plan_payloads(repo)
            for filename, payload in payloads.items():
                (plan / filename).write_bytes(payload)
            records = [
                {
                    "filename": filename,
                    "content_sha256": hashlib.sha256(payloads[filename]).hexdigest(),
                    "size_bytes": len(payloads[filename]),
                }
                for filename in audit_pilot.PLAN_PAYLOAD_FILES
            ]
            core = {
                "schema_version": protocol.PLAN_SCHEMA_VERSION,
                "study_slug": protocol.STUDY_SLUG,
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "status": "target_blind_pilot_plan_execution_bindings_unresolved",
                "files": records,
                "canonical_payload_sha256": protocol.canonical_sha256(
                    {
                        "schema_version": protocol.PLAN_SCHEMA_VERSION,
                        "study_id": protocol.STUDY_ID,
                        "protocol_version": protocol.PROTOCOL_VERSION,
                        "files": records,
                    }
                ),
                "hash_semantics": {
                    "content_sha256": "SHA-256 of exact file bytes, including the final newline",
                    "canonical_payload_sha256": (
                        "SHA-256 of canonical JSON over schema/study/protocol and ordered file records"
                    ),
                    "plan_manifest_sha256": (
                        "SHA-256 of canonical JSON over this manifest excluding only this field"
                    ),
                },
            }
            manifest = {**core, "plan_manifest_sha256": protocol.canonical_sha256(core)}
            (plan / "PLAN_MANIFEST.json").write_bytes(
                protocol.canonical_json_bytes(manifest) + b"\n"
            )
            audit_pilot.validate_plan_independently(plan, repo_root=repo)
            (plan / "g1_plan.jsonl").write_bytes(
                (plan / "g1_plan.jsonl").read_bytes() + b"\n"
            )
            with self.assertRaises(audit_pilot.StructuralAuditError):
                audit_pilot.validate_plan_independently(plan, repo_root=repo)

        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "repo"
            for relative in audit_pilot.BOUND_REPOSITORY_PATHS:
                destination = copied / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(repo / relative, destination)
            payloads = audit_pilot._expected_plan_payloads(copied)
            (copied / audit_pilot.AUDIT_SOURCE_RELATIVE_PATH).write_text(
                "# drift\n", encoding="utf-8"
            )
            self.assertNotEqual(
                payloads["source_inventory.json"],
                audit_pilot._expected_plan_payloads(copied)["source_inventory.json"],
            )

    def test_phase_manifest_rehash_detects_byte_and_inventory_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "synthetic"
            directory.mkdir()
            started = {
                "study_id": protocol.STUDY_ID,
                "phase": "G1",
                "run_id": "synthetic",
                "plan_manifest_sha256": TEST_PLAN_MANIFEST_SHA256,
                "execution_binding_canonical_sha256": "b" * 64,
                "prior_outcome_inputs": [],
                "target_prompt_inputs": [],
                "target_outcome_inputs": [],
            }
            completed = {
                "study_id": protocol.STUDY_ID,
                "phase": "G1",
                "run_id": "synthetic",
                "row_counts": {"g1_rows.jsonl": 0},
                "analysis_decisions": [],
            }
            values = {
                "RUN_STARTED.json": started,
                "RUN_COMPLETE.json": completed,
                "TOKENIZER_AUDIT.json": {},
                "PHASE_BINDING.json": {},
                "RUNTIME_METADATA.json": {},
            }
            for name, value in values.items():
                (directory / name).write_bytes(protocol.canonical_json_bytes(value) + b"\n")
            (directory / "g1_rows.jsonl").write_bytes(b"")
            records = [
                {
                    "path": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path in sorted(directory.iterdir())
            ]
            core = {
                "schema_version": 1,
                "study_id": protocol.STUDY_ID,
                "phase": "G1",
                "run_id": "synthetic",
                "plan_manifest_sha256": TEST_PLAN_MANIFEST_SHA256,
                "execution_binding_canonical_sha256": "b" * 64,
                "row_counts": {"g1_rows.jsonl": 0},
                "files": records,
            }
            (directory / "FILE_MANIFEST.json").write_bytes(
                protocol.canonical_json_bytes(
                    {**core, "manifest_sha256": protocol.canonical_sha256(core)}
                )
                + b"\n"
            )
            audit_pilot._verify_completed_transaction(
                directory,
                phase="G1",
                run_id="synthetic",
                plan_hash=TEST_PLAN_MANIFEST_SHA256,
                execution_hash="b" * 64,
            )
            (directory / "TOKENIZER_AUDIT.json").write_bytes(b"{}\n\n")
            with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "bytes differ"):
                audit_pilot._verify_completed_transaction(
                    directory,
                    phase="G1",
                    run_id="synthetic",
                    plan_hash=TEST_PLAN_MANIFEST_SHA256,
                    execution_hash="b" * 64,
                )

    def test_full_matching_table_recomputes_mad_greedy_tie_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            protocol, "G4_TARGET_FEATURE_IDS", (0, 1)
        ), mock.patch.dict(protocol.SAE_SPEC, {"feature_count": 8}):
            rows = []
            transformed = [math.log1p(1.0), math.log1p(1.0), math.log1p(1.0), 0.5]
            for feature_id in range(8):
                rows.append(
                    {
                        "feature_id": feature_id,
                        "decoder_l2_norm": 1.0,
                        "mean_positive_activation": 1.0,
                        "max_positive_activation": 1.0,
                        "positive_activation_fraction": 0.5,
                        "transformed_coordinates": transformed,
                        "scaled_coordinates": [0.0, 0.0, 0.0, 0.0],
                        "eligible_candidate": feature_id not in {0, 1},
                        "exclusion_reasons": ["target_feature_id"] if feature_id in {0, 1} else [],
                    }
                )
            path = Path(temporary) / "table.jsonl"
            path.write_bytes(
                b"".join(protocol.canonical_json_bytes(row) + b"\n" for row in rows)
            )
            inventory = {
                "matching_candidate_inventory_sha256": protocol.canonical_sha256(rows),
                "target_to_matched": [
                    {"target_feature_id": 0, "matched_feature_id": 2, "scaled_distance": 0.0},
                    {"target_feature_id": 1, "matched_feature_id": 3, "scaled_distance": 0.0},
                ],
                "excluded_feature_ids": [0, 1],
            }
            audit_pilot.validate_g4_matching_table(path, inventory_receipt=inventory)
            inventory["target_to_matched"][1]["matched_feature_id"] = 4
            with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "tie break"):
                audit_pilot.validate_g4_matching_table(path, inventory_receipt=inventory)
            rows[2]["scaled_coordinates"][0] = 1.0
            path.write_bytes(
                b"".join(protocol.canonical_json_bytes(row) + b"\n" for row in rows)
            )
            with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "scaled coordinates"):
                audit_pilot.validate_g4_matching_table(path, inventory_receipt=inventory)

    def test_matching_table_accepts_and_reconstructs_zero_norm_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            protocol, "G4_TARGET_FEATURE_IDS", (0, 1)
        ), mock.patch.dict(protocol.SAE_SPEC, {"feature_count": 8}):
            base_transformed = [math.log1p(1.0), math.log1p(1.0), math.log1p(1.0), 0.5]
            rows = []
            for feature_id in range(8):
                zero_norm = feature_id == 2
                reasons = ["target_feature_id"] if feature_id in {0, 1} else []
                if zero_norm:
                    reasons.append("decoder_norm_nonfinite_or_nonpositive")
                transformed = list(base_transformed)
                if zero_norm:
                    transformed[0] = 0.0
                rows.append(
                    {
                        "feature_id": feature_id,
                        "decoder_l2_norm": 0.0 if zero_norm else 1.0,
                        "mean_positive_activation": 1.0,
                        "max_positive_activation": 1.0,
                        "positive_activation_fraction": 0.5,
                        "transformed_coordinates": transformed,
                        "scaled_coordinates": [
                            -math.log1p(1.0) if zero_norm else 0.0,
                            0.0,
                            0.0,
                            0.0,
                        ],
                        "eligible_candidate": not reasons,
                        "exclusion_reasons": reasons,
                    }
                )
            path = Path(temporary) / "table.jsonl"
            inventory = {
                "matching_candidate_inventory_sha256": protocol.canonical_sha256(rows),
                "target_to_matched": [
                    {"target_feature_id": 0, "matched_feature_id": 3, "scaled_distance": 0.0},
                    {"target_feature_id": 1, "matched_feature_id": 4, "scaled_distance": 0.0},
                ],
                "excluded_feature_ids": [0, 1],
            }

            def write_table(candidate_rows: list[dict[str, object]]) -> None:
                path.write_bytes(
                    b"".join(
                        protocol.canonical_json_bytes(row) + b"\n" for row in candidate_rows
                    )
                )

            write_table(rows)
            audited = audit_pilot.validate_g4_matching_table(
                path, inventory_receipt=inventory
            )
            self.assertEqual(
                audited[2]["exclusion_reasons"],
                ["decoder_norm_nonfinite_or_nonpositive"],
            )
            self.assertFalse(audited[2]["eligible_candidate"])
            self.assertEqual(inventory["excluded_feature_ids"], [0, 1])

            reason_tamper = copy.deepcopy(rows)
            reason_tamper[2]["exclusion_reasons"] = []
            write_table(reason_tamper)
            with self.assertRaisesRegex(
                audit_pilot.StructuralAuditError, "exclusion reasons"
            ):
                audit_pilot.validate_g4_matching_table(path, inventory_receipt=inventory)

            eligibility_tamper = copy.deepcopy(rows)
            eligibility_tamper[2]["eligible_candidate"] = True
            write_table(eligibility_tamper)
            with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "eligibility"):
                audit_pilot.validate_g4_matching_table(path, inventory_receipt=inventory)

    def test_vector_inventory_rejects_exclusion_norm_negation_and_preedit_tamper(self) -> None:
        receipt = vector_inventory_receipt()
        audit_pilot.validate_vector_inventory_receipt(
            receipt, plan_manifest_sha256=TEST_PLAN_MANIFEST_SHA256
        )
        mutations = (
            lambda value: value["excluded_feature_ids"].pop(),
            lambda value: value["vectors"][2].__setitem__("norm_relative_error", 0.5),
            lambda value: value["vectors"][0].__setitem__("signed_pair_exact_negation", False),
            lambda value: value["vectors"][0].__setitem__(
                "precomputed_before_any_edited_forward", False
            ),
        )
        for mutate in mutations:
            tampered = copy.deepcopy(receipt)
            mutate(tampered)
            _reseal(tampered)
            with self.assertRaises(audit_pilot.StructuralAuditError):
                audit_pilot.validate_vector_inventory_receipt(
                    tampered, plan_manifest_sha256=TEST_PLAN_MANIFEST_SHA256
                )

    def test_positive_synthetic_authorization_is_exact_and_self_hashed(self) -> None:
        token = tokenizer_audit_receipt()
        token_hash = token["receipt_sha256"]
        phases = ("G1", "G2", "G3", "G3P", "G4")
        phase_results = []
        for phase in phases:
            filenames = audit_pilot.PHASE_ROW_FILENAMES[phase]
            phase_results.append(
                {
                    "tokenizer_receipt": token,
                    "tokenizer_binding": {
                        "receipt_sha256": token_hash,
                        "token_ids": TEST_G1_TOKEN_IDS,
                        "semantic_endpoint_ids": {},
                    },
                    "vector_inventory_receipt": {} if phase == "G4" else None,
                    "vector_inventory_receipt_sha256": "e" * 64 if phase == "G4" else None,
                    "file_manifest": {
                        "file_manifest_content_sha256": phase.lower()[0] * 64,
                        "file_manifest_embedded_sha256": "f" * 64,
                    },
                    "measurement_files": {
                        filename: {
                            "row_count": 0,
                            "content_sha256": "1" * 64,
                            "logical_rows_sha256": "2" * 64,
                        }
                        for filename in filenames
                    },
                }
            )
        execution = {
            "execution_binding_canonical_sha256": "b" * 64,
            "tokenizer_content_inventory_sha256": "c" * 64,
            "tokenizer_audit_receipt_sha256": token_hash,
        }
        with mock.patch.object(
            audit_pilot,
            "validate_plan_independently",
            return_value={"plan_manifest_sha256": TEST_PLAN_MANIFEST_SHA256},
        ), mock.patch.object(
            audit_pilot,
            "_source_bindings",
            return_value=("3" * 64, "4" * 64),
        ), mock.patch.object(
            audit_pilot,
            "_validate_execution_and_artifacts",
            return_value=(execution, {"sae": Path("sae.pt")}),
        ), mock.patch.object(
            audit_pilot, "_audit_phase", side_effect=phase_results
        ):
            bundle = audit_pilot.audit_pilot(
                plan_dir=Path("plan"),
                execution_binding_path=Path("binding"),
                artifact_root=Path("artifacts"),
                volume_id="volume",
                phase_directories={phase: Path(phase) for phase in phases},
            )
        structural = bundle["structural_audit_receipt"]
        authorization = bundle["analysis_authorization"]
        structural_hash = structural.pop("receipt_sha256")
        self.assertEqual(structural_hash, protocol.canonical_sha256(structural))
        authorization_hash = authorization.pop("receipt_sha256")
        self.assertEqual(authorization_hash, protocol.canonical_sha256(authorization))
        self.assertEqual(
            authorization["structural_audit_receipt_sha256"], structural_hash
        )
        self.assertEqual(authorization["issuer"], protocol.STRUCTURAL_AUDIT_ISSUER)
        self.assertEqual(authorization["prior_outcome_inputs"], [])

    def test_audit_outputs_are_atomic_and_external_volume_bound(self) -> None:
        structural_core = {"status": "pass", "study_id": protocol.STUDY_ID}
        authorization_core = {"status": "authorized", "study_id": protocol.STUDY_ID}
        bundle = {
            "structural_audit_receipt": {
                **structural_core,
                "receipt_sha256": protocol.canonical_sha256(structural_core),
            },
            "analysis_authorization": {
                **authorization_core,
                "receipt_sha256": protocol.canonical_sha256(authorization_core),
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "volume"
            root.mkdir()
            (root / audit_pilot.VOLUME_SENTINEL).write_text(
                json.dumps(
                    {
                        "study_slug": protocol.STUDY_SLUG,
                        "study_id": protocol.STUDY_ID,
                        "volume_id": "volume-test",
                    }
                ),
                encoding="utf-8",
            )
            namespace = root / protocol.STUDY_SLUG / protocol.STUDY_ID
            namespace.mkdir(parents=True)
            output = namespace / "audit" / "audit-run-001"
            observed = audit_pilot.write_audit_outputs(
                output,
                bundle,
                artifact_root=root,
                volume_id="volume-test",
            )
            self.assertEqual(output.resolve(), observed)
            self.assertEqual(
                {
                    audit_pilot.STRUCTURAL_RECEIPT_FILENAME,
                    audit_pilot.ANALYSIS_AUTHORIZATION_FILENAME,
                },
                {path.name for path in output.iterdir()},
            )
            self.assertFalse(output.with_name(output.name + ".partial").exists())
            with self.assertRaisesRegex(
                audit_pilot.StructuralAuditError, "fresh direct child"
            ):
                audit_pilot.write_audit_outputs(
                    Path(temporary) / "outside-audit",
                    bundle,
                    artifact_root=root,
                    volume_id="volume-test",
                )

    def test_hook_tensor_bundle_rebuilds_pre_plus_vector_and_detects_byte_tamper(self) -> None:
        try:
            import torch
        except ImportError:
            self.skipTest("PyTorch is exercised in the pinned execution environment")
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(
            protocol.MODEL_SPEC, {"residual_width": 4}
        ):
            root = Path(temporary)
            vector = torch.tensor([0.5, -1.0, 2.0, -0.25], dtype=torch.bfloat16)
            pre = torch.zeros((1200, 4), dtype=torch.bfloat16)
            post = pre + vector
            tensor_path = root / "hooks.pt"
            torch.save({"pre_edit": pre, "post_edit": post}, tensor_path)
            pre_hash = audit_pilot._tensor_sha256_independent(pre[0])
            post_hash = audit_pilot._tensor_sha256_independent(post[0])
            index_rows = []
            telemetry = []
            for offset in range(1200):
                index_rows.append(
                    {
                        "tensor_row_index": offset,
                        "prompt_id": "neutral_01",
                        "subset_feature_ids": [1, 2],
                        "control_type": "target",
                        "sign": 1,
                        "pre_edit_sha256": pre_hash,
                        "post_edit_sha256": post_hash,
                    }
                )
                telemetry.append(
                    {
                        "prompt_id": "neutral_01",
                        "subset_feature_ids": [1, 2],
                        "control_type": "target",
                        "sign": 1,
                        "edited_pre_edit_sha256": pre_hash,
                        "clean_pre_edit_sha256": pre_hash,
                        "expected_post_edit_sha256": post_hash,
                        "observed_post_edit_sha256": post_hash,
                    }
                )
            index_path = root / "index.jsonl"
            index_path.write_bytes(
                b"".join(protocol.canonical_json_bytes(row) + b"\n" for row in index_rows)
            )
            vectors = {((1, 2), "target", 1): vector}
            audit_pilot.validate_g4_hook_tensors(
                tensor_path,
                index_path,
                telemetry_rows=telemetry,
                vectors=vectors,
            )
            post[17, 0] = post[17, 0] + 1
            tampered_path = root / "tampered.pt"
            torch.save({"pre_edit": pre, "post_edit": post}, tampered_path)
            with self.assertRaisesRegex(audit_pilot.StructuralAuditError, "hashes"):
                audit_pilot.validate_g4_hook_tensors(
                    tampered_path,
                    index_path,
                    telemetry_rows=telemetry,
                    vectors=vectors,
                )


if __name__ == "__main__":
    unittest.main()
