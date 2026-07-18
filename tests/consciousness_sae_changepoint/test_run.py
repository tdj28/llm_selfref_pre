"""Outcome-free tests for the sealed changepoint executor."""

from __future__ import annotations

import json
import math
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from experiments.consciousness_sae_changepoint import benchmark
from experiments.consciousness_sae_changepoint.protocol import (
    FIXED_TOKEN_CONDITIONS,
    MODEL_WIDTH,
    N_PREFIXES,
    PROTOCOL_VERSION,
    STUDY_ID,
    sampling_domain_hash,
)
from experiments.consciousness_sae_changepoint.run import (
    BlockPayload,
    ForwardTrace,
    GateValidationContext,
    GateValidationError,
    GateValidatorSpec,
    PinnedRuntime,
    PackedVocabularyPayload,
    PackedVocabularyRow,
    REPO_ROOT,
    SealedExecutionError,
    TraceSource,
    assert_content_free_status,
    bind_trace_predictions,
    choose_next_attempt,
    embedded_receipt_sha256,
    execute_stage2b_prefix,
    generate_probe,
    publish_block_payload,
    query_suffix_token_ids,
    sha256_json,
    switch_cleanup_guard,
    trace_prediction_binding,
    validate_freeze_receipt,
    validate_prefix_materialization_counts,
    validate_intervention_vector_inventory_gate,
    validate_prefix_bank_receipt,
    validate_registration_receipt,
    validate_target_blind_acceptance_receipt,
    vector_condition_key,
)
from experiments.consciousness_sae_changepoint.storage import sha256_file


def signed(payload: dict[str, object]) -> dict[str, object]:
    result = dict(payload)
    result["receipt_sha256"] = embedded_receipt_sha256(result)
    return result


class RegistrationGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan_hash = "a" * 64
        self.manifest_hash = "b" * 64
        self.commit = "c" * 40
        self.acceptance_hash = "d" * 64
        self.receipt = signed(
            {
                "schema_version": 1,
                "status": "registered",
                "study_id": STUDY_ID,
                "provider": "osf",
                "registration_id": "abc12",
                "registration_url": "https://osf.io/abc12/",
                "registered_at_utc": "2026-07-13T20:00:00+00:00",
                "plan_hash": self.plan_hash,
                "plan_manifest_sha256": self.manifest_hash,
                "pre_prefix_freeze_sha": self.commit,
                "acceptance_receipt_sha256": self.acceptance_hash,
            }
        )

    def validate(self, receipt: dict[str, object]) -> dict[str, object]:
        return validate_registration_receipt(
            receipt,
            plan_hash=self.plan_hash,
            plan_manifest_sha256=self.manifest_hash,
            pre_prefix_freeze_sha=self.commit,
            acceptance_receipt_sha256=self.acceptance_hash,
        )

    def test_registration_binds_plan_commit_and_timestamp(self) -> None:
        result = self.validate(self.receipt)
        self.assertEqual(result["registration_id"], "abc12")
        self.assertEqual(result["receipt_sha256"], self.receipt["receipt_sha256"])

    def test_registration_hash_is_self_validating(self) -> None:
        tampered = dict(self.receipt)
        tampered["plan_hash"] = "d" * 64
        with self.assertRaises(GateValidationError):
            self.validate(tampered)

    def test_registration_requires_zoned_nonfuture_time(self) -> None:
        for value in (
            "2026-07-13T20:00:00",
            (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        ):
            invalid = dict(self.receipt)
            invalid["registered_at_utc"] = value
            invalid["receipt_sha256"] = embedded_receipt_sha256(invalid)
            with self.subTest(value=value), self.assertRaises(GateValidationError):
                self.validate(invalid)


class FreezeGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan_hash = "e" * 64
        self.commit = "1" * 40
        self.acceptance_hash = "a" * 64
        self.receipt = signed(
            {
                "schema_version": 1,
                "status": "pass",
                "study_id": STUDY_ID,
                "freeze_kind": "pre_prefix",
                "local_commit_sha": self.commit,
                "remote_commit_sha": self.commit,
                "pushed": True,
                "tracked_tree_clean": True,
                "plan_hash": self.plan_hash,
                "acceptance_receipt_sha256": self.acceptance_hash,
                "verified_at_utc": "2026-07-13T20:01:00+00:00",
            }
        )

    def test_equal_local_remote_freeze_passes(self) -> None:
        result = validate_freeze_receipt(
            self.receipt,
            freeze_kind="pre_prefix",
            plan_hash=self.plan_hash,
            expected_acceptance_receipt_sha256=self.acceptance_hash,
        )
        self.assertEqual(result["commit_sha"], self.commit)

    def test_unequal_remote_or_unpushed_freeze_fails(self) -> None:
        for field, value in (("remote_commit_sha", "2" * 40), ("pushed", False)):
            invalid = dict(self.receipt)
            invalid[field] = value
            invalid["receipt_sha256"] = embedded_receipt_sha256(invalid)
            with self.subTest(field=field), self.assertRaises(GateValidationError):
                validate_freeze_receipt(
                    invalid,
                    freeze_kind="pre_prefix",
                    plan_hash=self.plan_hash,
                    expected_acceptance_receipt_sha256=self.acceptance_hash,
                )

    def test_second_freeze_must_bind_prefix_receipt(self) -> None:
        prefix_hash = "3" * 64
        second_commit = "4" * 40
        second = signed(
            {
                **{key: value for key, value in self.receipt.items() if key != "receipt_sha256"},
                "freeze_kind": "prefix_receipt",
                "local_commit_sha": second_commit,
                "remote_commit_sha": second_commit,
                "pre_prefix_freeze_sha": self.commit,
                "prefix_receipt_sha256": prefix_hash,
            }
        )
        result = validate_freeze_receipt(
            second,
            freeze_kind="prefix_receipt",
            plan_hash=self.plan_hash,
            expected_pre_prefix_sha=self.commit,
            expected_prefix_receipt_sha256=prefix_hash,
            expected_acceptance_receipt_sha256=self.acceptance_hash,
        )
        self.assertEqual(result["commit_sha"], second_commit)


class PrefixReceiptGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan_hash = "4" * 64
        self.commit = "5" * 40
        self.registration = "osf12"
        self.receipt = signed(
            {
                "schema_version": 1,
                "status": "pass",
                "study_id": STUDY_ID,
                "protocol_version": PROTOCOL_VERSION,
                "automatic_receipt": True,
                "content_included": False,
                "design_changes": [],
                "plan_hash": self.plan_hash,
                "pre_prefix_freeze_sha": self.commit,
                "registration_id": self.registration,
                "sampling_domain_hash": sampling_domain_hash(),
                "planned_prefixes": N_PREFIXES,
                "successful_prefixes": 158,
                "failed_prefixes": 2,
                "failure_code_counts": {"clean_prefix_early_eos": 2},
                "prefix_bank_manifest_sha256": "6" * 64,
                "prefix_bank_run_id": "prefix-bank-20260713",
            }
        )

    def validate(self, receipt: dict[str, object]) -> dict[str, object]:
        return validate_prefix_bank_receipt(
            receipt,
            plan_hash=self.plan_hash,
            pre_prefix_freeze_sha=self.commit,
            registration_id=self.registration,
        )

    def test_content_free_threshold_receipt_passes(self) -> None:
        result = self.validate(self.receipt)
        self.assertEqual(result["successful_prefixes"], 158)

    def test_threshold_and_design_changes_fail_closed(self) -> None:
        for changes in (None, ["changed dose"]):
            invalid = dict(self.receipt)
            if changes is None:
                invalid["successful_prefixes"] = 151
                invalid["failed_prefixes"] = 9
            else:
                invalid["design_changes"] = changes
            invalid["receipt_sha256"] = embedded_receipt_sha256(invalid)
            with self.subTest(changes=changes), self.assertRaises(GateValidationError):
                self.validate(invalid)


class TargetBlindAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.plan_hash = "7" * 64
        self.artifact_hash = "8" * 64
        self.calibration_hash = "9" * 64
        self.source_relative = "experiments/consciousness_sae_changepoint/run.py"
        self.source_path = REPO_ROOT / self.source_relative

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def fixture_validator(
        receipt: dict[str, object], context: GateValidationContext
    ) -> dict[str, object]:
        del context
        if receipt.get("gate_id") != "fixture_gate" or receipt.get("fixture_value") != 17:
            raise GateValidationError("fixture_gate", "fixture evidence differs")
        return {"fixture_value": 17}

    def receipt(self) -> dict[str, object]:
        child = signed(
            {
                "gate_schema_version": 1,
                "gate_id": "fixture_gate",
                "status": "pass",
                "study_id": STUDY_ID,
                "outcome_blind": True,
                "target_outcomes_opened": False,
                "prior_outcome_inputs": [],
                "plan_hash": self.plan_hash,
                "artifact_receipt_sha256": self.artifact_hash,
                "calibration_receipt_sha256": self.calibration_hash,
                "validator_id": "fixture_validator_v1",
                "fixture_value": 17,
            }
        )
        child_path = self.root / "fixture-gate.json"
        child_path.write_text(json.dumps(child, sort_keys=True) + "\n", encoding="utf-8")
        entry = {
            "gate_id": "fixture_gate",
            "validator_id": "fixture_validator_v1",
            "validator_source_path": self.source_relative,
            "validator_source_bytes": self.source_path.stat().st_size,
            "validator_source_sha256": sha256_file(self.source_path),
            "receipt_relative_path": child_path.name,
            "container_kind": "standalone_file",
            "container_relative_path": None,
            "bytes": child_path.stat().st_size,
            "sha256": sha256_file(child_path),
            "embedded_sha256": child["receipt_sha256"],
        }
        return signed(
            {
                "schema_version": 1,
                "status": "pass",
                "study_id": STUDY_ID,
                "outcome_blind": True,
                "target_outcomes_opened": False,
                "prior_outcome_inputs": [],
                "plan_hash": self.plan_hash,
                "artifact_receipt_sha256": self.artifact_hash,
                "calibration_receipt_sha256": self.calibration_hash,
                "created_at_utc": "2026-07-13T20:02:00+00:00",
                "gates": [entry],
            }
        )

    def validate(self, receipt: dict[str, object]):
        spec = GateValidatorSpec(
            gate_id="fixture_gate",
            validator_id="fixture_validator_v1",
            source_relative_path=self.source_relative,
            validate=self.fixture_validator,
        )
        return validate_target_blind_acceptance_receipt(
            receipt,
            plan_hash=self.plan_hash,
            artifact_receipt_sha256=self.artifact_hash,
            calibration_receipt_sha256=self.calibration_hash,
            artifact_root=self.root,
            validator_registry={(spec.gate_id, spec.validator_id): spec},
            required_gates=("fixture_gate",),
        )

    def test_manifest_opens_and_validates_external_child_receipt(self) -> None:
        receipt = self.receipt()
        validation = self.validate(receipt)
        self.assertEqual(validation.receipt_sha256, receipt["receipt_sha256"])
        self.assertEqual(
            validation.gate_receipt_sha256["fixture_gate"],
            receipt["gates"][0]["embedded_sha256"],  # type: ignore[index]
        )

    def test_tampered_child_and_unsupported_validator_fail_closed(self) -> None:
        tampered = self.receipt()
        (self.root / "fixture-gate.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaises(GateValidationError):
            self.validate(tampered)

        unsupported = self.receipt()
        unsupported["gates"][0]["validator_id"] = "unregistered"  # type: ignore[index]
        unsupported["receipt_sha256"] = embedded_receipt_sha256(unsupported)
        with self.assertRaises(GateValidationError):
            self.validate(unsupported)


class VectorInventoryValidatorTests(unittest.TestCase):
    def inventory(self) -> dict[str, object]:
        rows: list[dict[str, object]] = []
        for block_number in range(50):
            block_id = f"aggregate-{block_number:03d}"
            for condition_name in FIXED_TOKEN_CONDITIONS:
                if condition_name == "clean":
                    continue
                base = condition_name.removesuffix("_calibrated")
                sign = -1 if base.endswith("_supp") else 1
                role = (
                    "target_sae"
                    if base.startswith("target_")
                    else "matched_sae"
                    if base.startswith("matched_")
                    else "isotropic_residual"
                )
                key = vector_condition_key(block_id, condition_name)
                rows.append(
                    {
                        "condition_key": key,
                        "aggregate_block_id": block_id,
                        "condition_name": condition_name,
                        "intervention_role": role,
                        "dose_scale": (
                            "calibrated_sensitivity"
                            if condition_name.endswith("_calibrated")
                            else "literal"
                        ),
                        "sign": sign,
                        "requested_coefficients": [sign * 0.4, sign * 0.6],
                        "vector_dtype": "bfloat16",
                        "vector_sha256": sha256_json([key]),
                        "vector_l2_norm": math.sqrt(MODEL_WIDTH),
                        "vector_rms": 1.0,
                    }
                )
        rows.sort(key=lambda row: str(row["condition_key"]))
        return {
            "gate_schema_version": 1,
            "gate_id": "intervention_vector_inventory",
            "algorithm": (
                "numpy.PCG64/default_rng float32 unit vector scaled to the BF16 "
                "target-aggregate L2 norm, signed, then cast to BF16"
            ),
            "rows": rows,
            "inventory_sha256": sha256_json(rows),
        }

    def test_exact_50_by_12_inventory_passes(self) -> None:
        receipt = self.inventory()
        result = validate_intervention_vector_inventory_gate(
            receipt,
            GateValidationContext("a" * 64, "b" * 64, "c" * 64, Path("/tmp")),
        )
        self.assertEqual(len(result["rows"]), 600)

    def test_sign_or_coefficient_substitution_fails_static_validation(self) -> None:
        for field, value in (
            ("sign", -1),
            ("requested_coefficients", [-0.4, -0.6]),
        ):
            receipt = self.inventory()
            row = receipt["rows"][0]  # type: ignore[index]
            original = row[field]
            row[field] = value if original != value else 1  # type: ignore[index]
            receipt["inventory_sha256"] = sha256_json(receipt["rows"])
            with self.subTest(field=field), self.assertRaises(GateValidationError):
                validate_intervention_vector_inventory_gate(
                    receipt,
                    GateValidationContext("a" * 64, "b" * 64, "c" * 64, Path("/tmp")),
                )

    def test_vector_hash_substitution_fails_runtime_reconstruction(self) -> None:
        inventory = self.inventory()
        fixed_rows: list[dict[str, object]] = []
        for record in inventory["rows"]:  # type: ignore[union-attr]
            fixed_rows.append(
                {
                    "aggregate_block_id": record["aggregate_block_id"],
                    "condition_name": record["condition_name"],
                    "condition": {
                        "intervention_role": record["intervention_role"],
                        "dose_scale": record["dose_scale"],
                        "requested_coefficients": record["requested_coefficients"],
                    },
                }
            )
        runtime = object.__new__(PinnedRuntime)

        class FakeCuda:
            @staticmethod
            def empty_cache() -> None:
                return None

        runtime.torch = types.SimpleNamespace(cuda=FakeCuda())
        runtime._construct_intervention_vector = types.MethodType(
            lambda _self, condition: condition, runtime
        )

        def record(
            _self: PinnedRuntime,
            *,
            aggregate_block_id: str,
            condition_name: str,
            condition: dict[str, object],
            vector: object,
        ) -> dict[str, object]:
            del vector
            key = vector_condition_key(aggregate_block_id, condition_name)
            sign = (
                -1
                if condition_name.removesuffix("_calibrated").endswith("_supp")
                else 1
            )
            return {
                "condition_key": key,
                "aggregate_block_id": aggregate_block_id,
                "condition_name": condition_name,
                "intervention_role": condition["intervention_role"],
                "dose_scale": condition["dose_scale"],
                "sign": sign,
                "requested_coefficients": condition["requested_coefficients"],
                "vector_dtype": "bfloat16",
                "vector_sha256": sha256_json([key]),
                "vector_l2_norm": math.sqrt(MODEL_WIDTH),
                "vector_rms": 1.0,
            }

        runtime.vector_record = types.MethodType(record, runtime)
        inventory["rows"][0]["vector_sha256"] = "f" * 64  # type: ignore[index]
        inventory["inventory_sha256"] = sha256_json(inventory["rows"])
        with self.assertRaisesRegex(SealedExecutionError, "reconstructed intervention"):
            runtime.validate_vector_inventory(fixed_rows, inventory)

        valid_inventory = self.inventory()
        runtime.validate_vector_inventory(fixed_rows, valid_inventory)
        source = next(
            row for row in fixed_rows if row["condition_name"] == "target_amp"
        )
        wrong_key_row = next(
            row for row in fixed_rows if row["condition_name"] == "matched_amp"
        )
        wrong_key = vector_condition_key(
            str(wrong_key_row["aggregate_block_id"]),
            str(wrong_key_row["condition_name"]),
        )
        with self.assertRaisesRegex(SealedExecutionError, "frozen plan row"):
            runtime.intervention_vector(source["condition"], condition_key=wrong_key)


class SealingAndResumeTests(unittest.TestCase):
    class FakeBlock:
        def __init__(
            self,
            root: Path,
            block_id: str,
            *,
            fail_before_rename: bool = False,
            fail_after_rename: bool = False,
        ):
            self.block_id = block_id
            self.partial_path = root / f"{block_id}.partial"
            self.final_path = root / block_id
            self.partial_path.mkdir()
            self.fail_before_rename = fail_before_rename
            self.fail_after_rename = fail_after_rename
            self.complete_calls: list[dict[str, object]] = []

        def write_json(self, relative: str, value: object) -> Path:
            path = self.partial_path / relative
            path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
            return path

        def complete(self, *, metadata: dict[str, object] | None = None) -> Path:
            self.complete_calls.append(dict(metadata or {}))
            if self.fail_before_rename and (metadata or {}).get("status") != "fail":
                (self.partial_path / "BLOCK_MANIFEST.json").write_text(
                    "{}\n", encoding="utf-8"
                )
                raise RuntimeError("injected failure after manifest, before rename")
            self.partial_path.rename(self.final_path)
            if self.fail_after_rename:
                raise RuntimeError("injected failure after publication rename")
            return self.final_path

    class FakeRun:
        def __init__(
            self,
            root: Path,
            *,
            fail_before_rename: bool = False,
            fail_after_rename: bool = False,
        ):
            self.root = root
            self.fail_before_rename = fail_before_rename
            self.fail_after_rename = fail_after_rename
            self.begin_calls = 0
            self.blocks: list[SealingAndResumeTests.FakeBlock] = []

        def begin_block(self, block_id: str):
            self.begin_calls += 1
            block = SealingAndResumeTests.FakeBlock(
                self.root,
                block_id,
                fail_before_rename=self.fail_before_rename,
                fail_after_rename=self.fail_after_rename,
            )
            self.blocks.append(block)
            return block

    def test_stdout_allowlist_rejects_raw_content(self) -> None:
        assert_content_free_status(
            {
                "status": "pass",
                "prefix_token_ids_sha256": "a" * 64,
                "failure_code_counts": {},
            }
        )
        for payload in (
            {"text": "synthetic fixture"},
            {"nested": {"token_ids": [1, 2]}},
            {"rows": [{"logits": [0.1]}]},
        ):
            with self.subTest(payload=payload), self.assertRaises(SealedExecutionError):
                assert_content_free_status(payload)

    def test_whole_block_attempt_policy(self) -> None:
        self.assertEqual(choose_next_attempt([]), 0)
        self.assertEqual(choose_next_attempt([{"attempt": 0, "status": "fail"}]), 1)
        self.assertIsNone(
            choose_next_attempt(
                [
                    {"attempt": 0, "status": "fail"},
                    {"attempt": 1, "status": "fail"},
                ]
            )
        )
        self.assertIsNone(choose_next_attempt([{"attempt": 0, "status": "pass"}]))

    def test_write_and_preseal_failures_abort_the_same_open_block(self) -> None:
        for injected_stage in ("before_json", "before_seal"):
            with self.subTest(stage=injected_stage), tempfile.TemporaryDirectory() as temporary:
                run = self.FakeRun(Path(temporary))
                payload = BlockPayload(
                    metadata={"status": "pass", "prefix_id": "prefix-000"},
                    json_files={"payload.json": {"safe": True}},
                    traces=[],
                )

                def inject(stage: str, _block: object) -> None:
                    if stage == injected_stage:
                        raise RuntimeError(f"injected {stage}")

                with patch(
                    "experiments.consciousness_sae_changepoint.run._write_trace_shards",
                    return_value=[],
                ):
                    published, failure = publish_block_payload(
                        run=run,  # type: ignore[arg-type]
                        block_id="prefix-000-attempt-0",
                        payload=payload,
                        attempt=0,
                        failure_injector=inject,
                    )
                self.assertFalse(published)
                self.assertEqual(failure, "archive_write_failure")
                self.assertEqual(run.begin_calls, 1)
                self.assertEqual(len(run.blocks[0].complete_calls), 1)
                self.assertEqual(run.blocks[0].complete_calls[0]["status"], "fail")
                self.assertTrue(run.blocks[0].final_path.is_dir())

    def test_failure_after_rename_is_fatal_and_never_reopens_block_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = self.FakeRun(Path(temporary), fail_after_rename=True)
            payload = BlockPayload(
                metadata={"status": "pass", "prefix_id": "prefix-000"},
                json_files={"payload.json": {"safe": True}},
                traces=[],
            )
            with patch(
                "experiments.consciousness_sae_changepoint.run._write_trace_shards",
                return_value=[],
            ), self.assertRaisesRegex(SealedExecutionError, "partial namespace") as caught:
                publish_block_payload(
                    run=run,  # type: ignore[arg-type]
                    block_id="prefix-000-attempt-0",
                    payload=payload,
                    attempt=0,
                )
            self.assertEqual(caught.exception.code, "archive_seal_failure")
            self.assertEqual(run.begin_calls, 1)

    def test_failure_after_manifest_aborts_same_block_and_preserves_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = self.FakeRun(Path(temporary), fail_before_rename=True)
            payload = BlockPayload(
                metadata={"status": "pass", "prefix_id": "prefix-000"},
                json_files={"payload.json": {"safe": True}},
                traces=[],
            )
            with patch(
                "experiments.consciousness_sae_changepoint.run._write_trace_shards",
                return_value=[],
            ):
                published, failure = publish_block_payload(
                    run=run,  # type: ignore[arg-type]
                    block_id="prefix-000-attempt-0",
                    payload=payload,
                    attempt=0,
                )
            self.assertFalse(published)
            self.assertEqual(failure, "archive_write_failure")
            self.assertEqual(run.begin_calls, 1)
            self.assertEqual(len(run.blocks[0].complete_calls), 2)
            self.assertEqual(run.blocks[0].complete_calls[-1]["status"], "fail")
            self.assertTrue(
                (run.blocks[0].final_path / "failed-pass-manifest-00.json").is_file()
            )


class HookCleanupTests(unittest.TestCase):
    class FakeSwitch:
        def __init__(self) -> None:
            self.exited = False

        def __exit__(self, *_args: object) -> None:
            self.exited = True

    class FakeRuntime:
        def __init__(self) -> None:
            self._active_switches: list[HookCleanupTests.FakeSwitch] = []

    def _raising_side_effect(self, runtime: "HookCleanupTests.FakeRuntime", location: str):
        def raise_at_location(*_args: object, **_kwargs: object) -> None:
            switch = self.FakeSwitch()
            runtime._active_switches.append(switch)
            raise SealedExecutionError(
                f"injected_{location}", f"injected {location} failure"
            )

        return raise_at_location

    def test_probe_history_query_and_answer_failures_remove_hooks(self) -> None:
        for location in ("history", "query", "answer"):
            runtime = self.FakeRuntime()
            with self.subTest(location=location), patch(
                "experiments.consciousness_sae_changepoint.run._generate_probe_unchecked",
                side_effect=self._raising_side_effect(runtime, location),
            ), self.assertRaises(SealedExecutionError):
                generate_probe(
                    runtime,  # type: ignore[arg-type]
                    {},
                    None,
                    None,
                    clean_cache=None,
                    expected_cache_sha256="a" * 64,
                    pending_y95=0,
                )
            self.assertEqual(runtime._active_switches, [])

    def test_fixed_forward_failure_removes_hook(self) -> None:
        runtime = self.FakeRuntime()
        with patch(
            "experiments.consciousness_sae_changepoint.run._execute_stage2b_prefix_unchecked",
            side_effect=self._raising_side_effect(runtime, "fixed"),
        ), self.assertRaises(SealedExecutionError):
            execute_stage2b_prefix(
                runtime,  # type: ignore[arg-type]
                prefix_payload={},
                fixed_rows=[],
            )
        self.assertEqual(runtime._active_switches, [])


class QuerySuffixTests(unittest.TestCase):
    class FakeTokenizer:
        def apply_chat_template(self, messages: object, **kwargs: object) -> list[int]:
            del messages, kwargs
            return [10, 11, 12, 90, 91, 92]

    def test_suffix_is_exact_tail_after_open_assistant_prefix(self) -> None:
        self.assertEqual(query_suffix_token_ids(self.FakeTokenizer(), [10, 11, 12]), [90, 91, 92])

    def test_suffix_rejects_template_prefix_change(self) -> None:
        with self.assertRaises(SealedExecutionError):
            query_suffix_token_ids(self.FakeTokenizer(), [10, 99])


class SourceIndexBindingTests(unittest.TestCase):
    def trace(self) -> ForwardTrace:
        rows = benchmark.build_representative_source_index_rows(
            [
                *[f"{layer}_post" for layer in range(45, 50)],
                "50_pre",
                "50_post",
                *[f"{layer}_post" for layer in range(51, 79)],
                "final_pre_norm",
            ],
            plan_hash="a" * 64,
            run_id="neutral-source-test",
            prefix_token_ids_sha256="b" * 64,
            predicted_token_id=42,
            intervention_sha256="c" * 64,
            parent_cache_sha256="d" * 64,
            output_cache_sha256="e" * 64,
        )
        sources: list[TraceSource] = []
        for row in rows:
            unbound = dict(row)
            unbound.update(
                {
                    "predicted_token_id": -1,
                    "paired_stream_id": "unbound",
                    "decode_step": -1,
                    "uniform_receipt_sha256": "0" * 64,
                }
            )
            sources.append(
                TraceSource(
                    row={field: unbound[field] for field in benchmark.SOURCE_INDEX_FIELDS},
                    residual=None,
                    lineage={"row_id": row["row_id"], "fixture": True},
                )
            )
        return ForwardTrace(
            sources=sources,
            selected_actual_logits={},
            output=None,
            output_cache_sha256="e" * 64,
        )

    def test_prediction_binding_finalizes_exact_benchmark_schema(self) -> None:
        traced = self.trace()
        binding = trace_prediction_binding(
            predicted_token_id=42,
            prefix_seed=2_026_071_398,
            paired_stream_id="neutral-main-benchmark",
            decode_step=2,
        )
        bind_trace_predictions(traced, {"event0": binding})
        self.assertEqual(len(traced.sources), 36)
        for source in traced.sources:
            self.assertEqual(tuple(source.row), benchmark.SOURCE_INDEX_FIELDS)
            self.assertEqual(source.row["predicted_token_id"], 42)
            self.assertNotIn("lineage_sha256", source.row)
            self.assertEqual(source.lineage["row_id"], source.row["row_id"])
            self.assertRegex(source.lineage["lineage_sha256"], r"^[0-9a-f]{64}$")

    def test_binding_with_another_prefix_seed_fails(self) -> None:
        traced = self.trace()
        wrong = trace_prediction_binding(
            predicted_token_id=42,
            prefix_seed=2_026_071_399,
            paired_stream_id="neutral-main-benchmark",
            decode_step=2,
        )
        with self.assertRaisesRegex(SealedExecutionError, "another prefix seed"):
            bind_trace_predictions(traced, {"event0": wrong})


class PrefixMaterializationCountTests(unittest.TestCase):
    def stage2b_fixture(self):
        state_rows = benchmark.build_representative_source_index_rows(
            [
                *[f"{layer}_post" for layer in range(45, 50)],
                "50_pre",
                "50_post",
                *[f"{layer}_post" for layer in range(51, 79)],
                "final_pre_norm",
            ],
            plan_hash="a" * 64,
            run_id="count-test",
            prefix_token_ids_sha256="b" * 64,
            predicted_token_id=42,
            intervention_sha256="c" * 64,
            parent_cache_sha256="d" * 64,
            output_cache_sha256="e" * 64,
        )
        traces: list[TraceSource] = []
        for position_index in range(26):
            checkpoint = "fixed_prequery" if position_index < 13 else "fixed_answer"
            for state_index, template in enumerate(state_rows):
                row = dict(template)
                row["row_id"] = sha256_json(
                    ["count-row", position_index, state_index]
                )[:32]
                row["forward_id"] = f"fixed-forward-{position_index:02d}"
                row["capture_position"] = checkpoint
                traces.append(
                    TraceSource(
                        row={field: row[field] for field in benchmark.SOURCE_INDEX_FIELDS},
                        residual=None,
                        lineage={"row_id": row["row_id"]},
                    )
                )
        j_ids = [
            source.row["row_id"]
            for source in traces
            if isinstance(source.row["j_map_layer"], int)
        ]
        jlens_rows = [{"source_row_id": row_id} for row_id in j_ids]
        random_rows = [
            {"source_row_id": row_id, "random_transport_seed": seed}
            for row_id in j_ids
            for seed in benchmark.RANDOM_TRANSPORT_SEEDS
        ]
        packed_rows = [
            PackedVocabularyRow(
                metadata={"logical_kind": "raw_topk", "k": 2000}, tensors={}
            )
            for _ in range(910)
        ] + [
            PackedVocabularyRow(
                metadata={"logical_kind": "pair_delta_union", "k": 2000}, tensors={}
            )
            for _ in range(980)
        ]
        return traces, jlens_rows, random_rows, PackedVocabularyPayload(packed_rows)

    def test_exact_stage2b_26_by_36_ledger_passes(self) -> None:
        traces, jlens, random_j, packed = self.stage2b_fixture()
        result = validate_prefix_materialization_counts(
            stage="stage2b",
            traces=traces,
            jlens_rows=jlens,
            random_j_rows=random_j,
            packed=packed,
        )
        self.assertEqual(result["source_positions"], 26)
        self.assertEqual(result["source_rows"], 936)
        self.assertEqual(result["jlens_rows"], 910)
        self.assertEqual(result["random_j_rows"], 4_550)
        self.assertEqual(result["packed_vocab_rows"], 1_890)

    def test_one_missing_source_row_fails_closed(self) -> None:
        traces, jlens, random_j, packed = self.stage2b_fixture()
        with self.assertRaisesRegex(SealedExecutionError, "source rows differ"):
            validate_prefix_materialization_counts(
                stage="stage2b",
                traces=traces[:-1],
                jlens_rows=jlens,
                random_j_rows=random_j,
                packed=packed,
            )


try:
    import numpy as np
    import torch
except ImportError:  # pragma: no cover - local lightweight environment
    np = None
    torch = None


@unittest.skipIf(
    torch is None or np is None or not torch.cuda.is_available(),
    "isotropic fixture requires a CUDA torch runtime",
)
class IsotropicVectorTests(unittest.TestCase):
    def runtime(self) -> PinnedRuntime:
        runtime = object.__new__(PinnedRuntime)
        runtime.torch = torch
        runtime.np = np
        generator = torch.Generator(device="cpu")
        generator.manual_seed(77)
        runtime.sae_decoder = torch.randn(8, 16, generator=generator, dtype=torch.float32)
        return runtime

    def condition(self, sign: int) -> dict[str, object]:
        return {
            "intervention_role": "isotropic_residual",
            "target_anchor_feature_ids": [1, 3],
            "requested_coefficients": [sign * 0.4, sign * 0.6],
            "isotropic_vector_seed": 991,
        }

    def test_seeded_isotropic_is_deterministic_norm_matched_and_signed(self) -> None:
        runtime = self.runtime()
        # The production contract is width 8192. Patch the tiny synthetic
        # decoder to that width without using any outcome text or prior result.
        runtime.sae_decoder = torch.randn(8192, 16, generator=torch.Generator().manual_seed(7))
        positive = runtime._construct_intervention_vector(self.condition(1)).cpu().float()
        repeated = runtime._construct_intervention_vector(self.condition(1)).cpu().float()
        negative = runtime._construct_intervention_vector(self.condition(-1)).cpu().float()
        self.assertTrue(torch.equal(positive, repeated))
        self.assertTrue(torch.equal(negative, -positive))
        target = (
            runtime.sae_decoder[:, [1, 3]]
            * torch.tensor([0.4, 0.6]).unsqueeze(0)
        ).sum(dim=1)
        # BF16 quantization makes exact norm equality inappropriate; the
        # receipt's vector hash is exact and the norm remains close.
        self.assertLess(abs(positive.norm().item() - target.norm().item()) / target.norm().item(), 0.01)


if __name__ == "__main__":
    unittest.main()
