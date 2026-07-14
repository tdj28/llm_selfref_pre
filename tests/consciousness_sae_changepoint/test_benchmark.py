from __future__ import annotations

import copy
import hashlib
import importlib.util
import inspect
import math
import unittest
from decimal import Decimal

from experiments.consciousness_sae_changepoint import benchmark
from experiments.consciousness_sae_changepoint.protocol import canonical_json_bytes


PLAN_HASH = "a" * 64
SOURCE_HASH = "b" * 64
VOLUME_ID = "lens-campaign"


def _trace_labels() -> list[str]:
    return [
        *(f"{layer}_post" for layer in range(45, 50)),
        "50_pre",
        "50_post",
        *(f"{layer}_post" for layer in range(51, 79)),
        "final_pre_norm",
    ]


class ExactBenchmarkWorkloadTests(unittest.TestCase):
    def test_exact_n160_role_source_and_vocabulary_ledger(self) -> None:
        workload = benchmark.build_exact_workload(160)
        expected = {
            "prefixes": 160,
            "main_branches": 1_280,
            "disposable_probes": 6_560,
            "fixed_token_forwards": 2_080,
            "clean_prefix_sampled_tokens": 15_360,
            "main_post_event_sampled_tokens_max": 81_920,
            "binary_answer_sampled_tokens_max": 1_679_360,
            "natural_judge_items": 2_560,
            "binary_judge_items": 6_560,
            "local_judge_base_items": 9_120,
            "local_judge_invocations_max": 18_240,
            "local_judge_output_tokens_max": 1_167_360,
            "experiment_prefill_tokens_max": 921_600,
            "local_judge_prefill_tokens_max": 14_008_320,
            "sampled_decode_tokens_including_judge_max": 2_944_000,
            "pre_window_positions_per_prefix": 32,
            "main_positions_per_prefix": 512,
            "probe_positions_per_prefix": 41,
            "fixed_positions_per_prefix": 26,
            "source_positions_per_prefix": 611,
            "source_states_per_position": 36,
            "j_source_states_per_position": 35,
            "jlens_source_rows": 3_421_600,
            "real_j_readout_rows": 3_421_600,
            "identity_readout_rows": 3_421_600,
            "random_j_readout_rows": 1_232_000,
            "final_source_rows": 97_760,
            "total_source_rows": 3_519_360,
            "source_width": 8_192,
            "exact_bf16_source_payload_bytes": 57_661_194_240,
            "raw_vocab_rows_k512": 168_000,
            "raw_vocab_rows_k2000": 246_400,
            "raw_vocab_rows_total": 414_400,
            "pair_contrast_rows_k512": 100_800,
            "pair_contrast_rows_k2000": 201_600,
            "sign_contrast_rows_k512": 16_800,
            "sign_contrast_rows_k2000": 33_600,
            "contrast_rows_total": 352_800,
            "raw_topk_entries_max": 578_816_000,
            "pair_union_entries_max": 909_619_200,
            "sign_union_entries_max": 151_603_200,
        }
        self.assertEqual(workload.as_dict(), expected)
        self.assertEqual(
            workload.random_j_readout_rows,
            160 * 44 * 35 * 5,
        )

    def test_n560_is_a_linear_prospective_expansion_not_old_data(self) -> None:
        n160 = benchmark.build_exact_workload(160)
        n560 = benchmark.build_exact_workload(560)
        invariant_fields = {
            "pre_window_positions_per_prefix",
            "main_positions_per_prefix",
            "probe_positions_per_prefix",
            "fixed_positions_per_prefix",
            "source_positions_per_prefix",
            "source_states_per_position",
            "j_source_states_per_position",
            "source_width",
        }
        for field, value in n160.as_dict().items():
            with self.subTest(field=field):
                if field in invariant_fields:
                    self.assertEqual(getattr(n560, field), value)
                else:
                    self.assertEqual(getattr(n560, field), value * 7 // 2)
        self.assertEqual(n560.main_branches, 4_480)
        self.assertEqual(n560.disposable_probes, 22_960)
        self.assertEqual(n560.fixed_token_forwards, 7_280)
        self.assertEqual(n560.total_source_rows, 12_317_760)
        self.assertEqual(n560.jlens_source_rows, 11_975_600)
        self.assertEqual(n560.random_j_readout_rows, 4_312_000)
        self.assertEqual(n560.raw_vocab_rows_k512, 588_000)
        self.assertEqual(n560.raw_vocab_rows_k2000, 862_400)
        self.assertEqual(n560.contrast_rows_total, 1_234_800)
        self.assertEqual(n560.exact_bf16_source_payload_bytes, 201_814_179_840)

    def test_default_n_is_derived_from_the_current_protocol(self) -> None:
        self.assertEqual(
            benchmark.build_exact_workload(),
            benchmark.build_exact_workload(benchmark.N_PREFIXES),
        )
        with self.assertRaises(benchmark.BenchmarkContractError):
            benchmark.build_exact_workload(0)
        with self.assertRaises(benchmark.BenchmarkContractError):
            benchmark.build_exact_workload(True)

    def test_prefill_limits_do_not_double_count_fixed_forwards(self) -> None:
        workload = benchmark.build_exact_workload(160)
        self.assertEqual(
            workload.experiment_prefill_tokens_max,
            160 * 512 + 6_560 * 128,
        )
        self.assertEqual(workload.local_judge_prefill_tokens_max, 18_240 * 768)
        self.assertNotIn("fixed_prefill_tokens", workload.as_dict())

    def test_neutral_packed_fixture_covers_all_checkpoints_and_contrasts(self) -> None:
        rows = benchmark._expected_packed_fixture_rows()
        self.assertEqual(len(rows), 98)
        self.assertEqual(
            {row["checkpoint"] for row in rows},
            set(benchmark.VOCABULARY_CHECKPOINTS),
        )
        for checkpoint in benchmark.VOCABULARY_CHECKPOINTS:
            checkpoint_rows = [row for row in rows if row["checkpoint"] == checkpoint]
            self.assertEqual(len(checkpoint_rows), 14)
            self.assertEqual(
                {row["k"] for row in checkpoint_rows},
                {benchmark.VOCABULARY_TOP_K_BY_CHECKPOINT[checkpoint]},
            )
            self.assertEqual(
                {row["contrast_id"] for row in checkpoint_rows if row["contrast_id"]},
                set(benchmark.VOCABULARY_CONTRASTS),
            )
        self.assertEqual(
            hashlib.sha256(canonical_json_bytes(rows)).hexdigest(),
            benchmark.PACKED_FIXTURE_INVENTORY_SHA256,
        )

    def test_neutral_packet_is_source_frozen(self) -> None:
        self.assertEqual(
            benchmark.NEUTRAL_PACKET_SPEC_SHA256,
            "6188f39e2b1569c71e6cc0ca4749afcf7a1f18701a7d9ffcc10fa93f8f55a6e8",
        )
        packet_text = " ".join(
            str(value) for value in benchmark.NEUTRAL_PACKET_SPEC.values()
        ).lower()
        for forbidden in ("conscious", "deception", "roleplay", "self-reference"):
            self.assertNotIn(forbidden, packet_text)

    def test_module_has_no_target_prompt_or_prior_result_dependency(self) -> None:
        source = inspect.getsource(benchmark)
        self.assertNotIn("SELF_REFERENCE_PROMPT", source)
        self.assertNotIn("BINARY_CONSCIOUS_QUERY", source)
        self.assertNotIn("data/public_sae_consciousness_gating", source)
        self.assertNotIn("data/sae_jlens_audit", source)
        self.assertNotIn("experiments/exp2_sae", source)
        self.assertNotIn("NON_RESIDUAL_STORAGE_FLOOR", source)
        self.assertIn('"prior_outcome_inputs": []', source)

    def test_cli_accepts_only_bindings_paths_identity_n_and_live_price(self) -> None:
        parsed = benchmark.parse_args(
            [
                "--cache-dir",
                "/volume/cache",
                "--artifact-root",
                "/volume/study",
                "--volume-id",
                VOLUME_ID,
                "--run-id",
                "targetblind-benchmark-01",
                "--plan-hash",
                PLAN_HASH,
                "--prefix-count",
                "560",
                "--gpu-hourly-usd",
                "5.89",
            ]
        )
        self.assertEqual(parsed.volume_id, VOLUME_ID)
        self.assertEqual(parsed.plan_hash, PLAN_HASH)
        self.assertEqual(parsed.prefix_count, 560)
        self.assertFalse(hasattr(parsed, "plan"))
        self.assertFalse(hasattr(parsed, "results"))
        self.assertFalse(hasattr(parsed, "prefix_bank"))


class SourceIndexContractTests(unittest.TestCase):
    @staticmethod
    def rows() -> list[dict[str, object]]:
        return benchmark.build_representative_source_index_rows(
            _trace_labels(),
            plan_hash=PLAN_HASH,
            run_id="targetblind-benchmark-01",
            prefix_token_ids_sha256="c" * 64,
            predicted_token_id=42,
            intervention_sha256="d" * 64,
            parent_cache_sha256="e" * 64,
            output_cache_sha256="f" * 64,
        )

    def test_representative_rows_bind_every_source_state_and_replay_identity(self) -> None:
        rows = self.rows()
        self.assertEqual(len(rows), 36)
        self.assertEqual(len({row["row_id"] for row in rows}), 36)
        for row in rows:
            self.assertEqual(tuple(row), benchmark.SOURCE_INDEX_FIELDS)
            self.assertEqual(row["plan_hash"], PLAN_HASH)
            self.assertEqual(row["run_id"], "targetblind-benchmark-01")
            self.assertEqual(row["block_id"], "neutral-bf16-archive")
            self.assertEqual(row["prefix_token_ids_sha256"], "c" * 64)
            self.assertEqual(row["predicted_token_id"], 42)
            self.assertEqual(row["intervention_sha256"], "d" * 64)
            self.assertEqual(row["parent_cache_sha256"], "e" * 64)
            self.assertEqual(row["output_cache_sha256"], "f" * 64)
            self.assertRegex(str(row["uniform_receipt_sha256"]), r"^[0-9a-f]{64}$")
        self.assertEqual(rows[0]["j_map_layer"], 45)
        self.assertEqual(rows[5]["state"], "pre_edit")
        self.assertEqual(rows[6]["state"], "post_edit")
        self.assertEqual(rows[-1]["state"], "final_pre_norm")
        self.assertIsNone(rows[-1]["j_map_layer"])

    def test_source_index_validator_rejects_schema_and_binding_tampering(self) -> None:
        row = self.rows()[0]
        mutations = []
        missing = dict(row)
        missing.pop("plan_hash")
        mutations.append(missing)
        bad_token = dict(row)
        bad_token["predicted_token_id"] = benchmark.TOKENIZER_SIZE
        mutations.append(bad_token)
        bad_layer = dict(row)
        bad_layer["j_map_layer"] = 44
        mutations.append(bad_layer)
        bad_state = dict(row)
        bad_state["layer_state"] = "46"
        mutations.append(bad_state)
        bad_cache = dict(row)
        bad_cache["parent_cache_sha256"] = "not-a-hash"
        mutations.append(bad_cache)
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(benchmark.BenchmarkContractError):
                    benchmark.validate_source_index_row(mutation)


@unittest.skipUnless(importlib.util.find_spec("torch"), "torch is not installed locally")
class PackedVocabularyPrimitiveTests(unittest.TestCase):
    def test_chunked_full_vocabulary_matches_dense_head(self) -> None:
        import torch

        hidden = torch.tensor([[1.0, 2.0], [-1.0, 0.5]])
        head = torch.arange(22, dtype=torch.float32).reshape(11, 2)
        observed = benchmark._chunked_full_vocab_logits(hidden, head, chunk_size=3)
        self.assertTrue(torch.equal(observed, hidden @ head.T))

    def test_raw_topk_is_stable_and_uses_int32_float32(self) -> None:
        import torch

        packed = benchmark._stable_raw_topk(
            torch.tensor([[3.0, 3.0, 2.0, -1.0]], dtype=torch.float16),
            k=2,
        )
        self.assertEqual(packed["token_ids"].tolist(), [[0, 1]])
        self.assertEqual(packed["token_ids"].dtype, torch.int32)
        self.assertEqual(packed["scores"].dtype, torch.float32)
        self.assertEqual(benchmark._packed_numeric_bytes(packed), 2 * 8)

    def test_pair_union_retains_both_arms_delta_and_tail_ranks(self) -> None:
        import torch

        left = torch.tensor([5.0, 0.0, 1.0, -3.0, 2.0])
        right = torch.zeros(5)
        packed = benchmark.pack_pair_delta_union(left, right, k=1)
        self.assertEqual(packed["token_ids"].tolist(), [0, 3])
        self.assertEqual(packed["left_scores"].tolist(), [5.0, -3.0])
        self.assertEqual(packed["right_scores"].tolist(), [0.0, 0.0])
        self.assertEqual(packed["delta"].tolist(), [5.0, -3.0])
        self.assertEqual(packed["positive_rank"].tolist(), [1, -1])
        self.assertEqual(packed["negative_rank"].tolist(), [-1, 1])
        self.assertEqual(benchmark._packed_numeric_bytes(packed), 2 * 24)

    def test_sign_union_retains_all_four_arm_scores(self) -> None:
        import torch

        target_supp = torch.tensor([8.0, 0.0, 0.0, -4.0])
        target_amp = torch.tensor([0.0, 0.0, 0.0, 2.0])
        matched_supp = torch.tensor([0.0, 0.0, 0.0, 2.0])
        matched_amp = torch.zeros(4)
        packed = benchmark.pack_four_arm_sign_union(
            target_supp,
            target_amp,
            matched_supp,
            matched_amp,
            k=1,
        )
        self.assertEqual(packed["token_ids"].tolist(), [0, 3])
        self.assertEqual(packed["delta"].tolist(), [4.0, -4.0])
        for field in (
            "target_supp_scores",
            "target_amp_scores",
            "matched_supp_scores",
            "matched_amp_scores",
        ):
            self.assertIn(field, packed)
        self.assertEqual(benchmark._packed_numeric_bytes(packed), 2 * 32)


class CapacityExtrapolationTests(unittest.TestCase):
    @staticmethod
    def metrics() -> dict[str, float]:
        return {
            "model_load_seconds": 60.0,
            "prefill_tokens_per_second": 50_000.0,
            "decode_tokens_per_second": 200.0,
            "fixed_forwards_per_second": 10.0,
            "real_j_states_per_second": 10_000.0,
            "identity_states_per_second": 50_000.0,
            "full_vocab_rows_per_second": 500.0,
            "raw_topk_k512_rows_per_second": 10_000.0,
            "raw_topk_k2000_rows_per_second": 10_000.0,
            "pair_union_k512_rows_per_second": 5_000.0,
            "pair_union_k2000_rows_per_second": 5_000.0,
            "sign_union_k512_rows_per_second": 5_000.0,
            "sign_union_k2000_rows_per_second": 5_000.0,
            "archive_write_bytes_per_second": 500_000_000.0,
            "archive_read_bytes_per_second": 800_000_000.0,
        }

    @staticmethod
    def archive_sample() -> dict[str, int]:
        return {
            "rows": 36,
            "residual_bytes": 36 * 8_192 * 2 + 104,
            "index_bytes": 12_000,
            "packed_arrays_bytes": 3_940_688,
            "packed_numeric_payload_bytes": 3_890_688,
            "packed_row_index_bytes": 12_000,
            "packed_row_count": 98,
            "token_metadata_bytes": 4_000_000,
        }

    def test_archive_projection_uses_exact_numeric_payload_and_measured_bytes(self) -> None:
        workload = benchmark.build_exact_workload(160)
        sample = self.archive_sample()
        projection = benchmark.estimate_archive_bytes(
            workload,
            sample_rows=sample["rows"],
            sample_residual_bytes=sample["residual_bytes"],
            sample_index_bytes=sample["index_bytes"],
            packed_arrays_bytes=sample["packed_arrays_bytes"],
            packed_numeric_payload_bytes=sample["packed_numeric_payload_bytes"],
            packed_row_index_bytes=sample["packed_row_index_bytes"],
            packed_row_count=sample["packed_row_count"],
            token_metadata_bytes=sample["token_metadata_bytes"],
        )
        self.assertEqual(projection["sample_residual_header_bytes"], 104)
        self.assertEqual(projection["source_index_bytes_per_row"], 334)
        self.assertEqual(projection["estimated_source_shards"], 430)
        self.assertEqual(projection["packed_vocab_logical_rows"], 767_200)
        self.assertEqual(projection["estimated_packed_vocab_shards"], 5_994)
        self.assertEqual(
            projection["exact_packed_numeric_payload_bytes"],
            31_312_691_200,
        )
        self.assertEqual(
            projection["packed_safetensors_overhead_bytes_per_row"], 511
        )
        self.assertEqual(
            projection["estimated_archive_bytes_before_failure_reserve"],
            90_639_801_200,
        )

    def test_measured_rates_expand_to_reproducible_reserved_ceilings(self) -> None:
        result = benchmark.extrapolate_capacity(
            self.metrics(),
            self.archive_sample(),
            gpu_hourly_usd=Decimal("5.89"),
            workload=benchmark.build_exact_workload(160),
        )
        self.assertEqual(result["failure_reserve_factor"], 1.5)
        self.assertAlmostEqual(
            result["estimated_gpu_hours_before_failure_reserve"],
            4.737713820527778,
        )
        self.assertEqual(result["hard_proposed_gpu_hour_ceiling"], 10)
        self.assertEqual(result["hard_proposed_spend_ceiling_usd"], "58.90")
        self.assertEqual(result["hard_proposed_storage_ceiling_gib"], 130)
        components = result["component_seconds_before_failure_reserve"]
        self.assertEqual(
            components["real_j_full_trace_selected_readouts"],
            3_421_600 / 10_000,
        )
        self.assertEqual(
            components["identity_full_trace_selected_readouts"],
            3_421_600 / 50_000,
        )
        self.assertEqual(
            components["five_random_j_direct_checkpoint_readouts"],
            1_232_000 / 10_000,
        )

    def test_n560_fails_current_150_gib_guard_before_launch(self) -> None:
        with self.assertRaisesRegex(
            benchmark.BenchmarkContractError,
            "storage proposal 450 GiB exceeds 150 GiB",
        ):
            benchmark.extrapolate_capacity(
                self.metrics(),
                self.archive_sample(),
                gpu_hourly_usd="5.89",
                workload=benchmark.build_exact_workload(560),
            )

    def test_every_required_rate_must_be_positive_and_finite(self) -> None:
        for key in self.metrics():
            with self.subTest(key=key):
                metrics = self.metrics()
                metrics[key] = math.nan
                with self.assertRaises(benchmark.BenchmarkContractError):
                    benchmark.extrapolate_capacity(
                        metrics,
                        self.archive_sample(),
                        gpu_hourly_usd="5.89",
                    )

    def test_slow_benchmark_fails_instead_of_raising_budget(self) -> None:
        metrics = self.metrics()
        metrics["decode_tokens_per_second"] = 1.0
        with self.assertRaisesRegex(
            benchmark.BenchmarkContractError,
            "GPU-hour proposal",
        ):
            benchmark.extrapolate_capacity(
                metrics,
                self.archive_sample(),
                gpu_hourly_usd="5.89",
            )

    def test_archive_projection_rejects_impossible_samples(self) -> None:
        workload = benchmark.build_exact_workload(160)
        sample = self.archive_sample()
        cases = (
            {**sample, "rows": 0},
            {**sample, "residual_bytes": 1},
            {**sample, "packed_arrays_bytes": 1},
        )
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(benchmark.BenchmarkContractError):
                    benchmark.estimate_archive_bytes(
                        workload,
                        sample_rows=case["rows"],
                        sample_residual_bytes=case["residual_bytes"],
                        sample_index_bytes=case["index_bytes"],
                        packed_arrays_bytes=case["packed_arrays_bytes"],
                        packed_numeric_payload_bytes=case[
                            "packed_numeric_payload_bytes"
                        ],
                        packed_row_index_bytes=case["packed_row_index_bytes"],
                        packed_row_count=case["packed_row_count"],
                        token_metadata_bytes=case["token_metadata_bytes"],
                    )

    def test_live_price_must_be_positive(self) -> None:
        with self.assertRaises(benchmark.BenchmarkContractError):
            benchmark.extrapolate_capacity(
                self.metrics(),
                self.archive_sample(),
                gpu_hourly_usd="0",
            )


class ReceiptValidationTests(unittest.TestCase):
    @classmethod
    def _receipt(cls) -> dict[str, object]:
        workload = benchmark.build_exact_workload(160)
        metrics = CapacityExtrapolationTests.metrics()
        flat_sample = CapacityExtrapolationTests.archive_sample()
        capacity = benchmark.extrapolate_capacity(
            metrics,
            flat_sample,
            gpu_hourly_usd="5.89",
            workload=workload,
        )
        gates = {
            "b200_single_gpu": True,
            "local_only_artifacts": True,
            "bf16_model_sae_and_real_j": True,
            "manual_incremental_decode": True,
            "one_nonzero_masked_layer50_call": True,
            "trace_45_49_50pre_50post_51_78_final": True,
            "real_j_selected_readout": True,
            "identity_full_trace_costed": True,
            "five_random_j_direct_positions_costed": True,
            "chunked_full_vocabulary_logits": True,
            "raw_k512_and_k2000_packed": True,
            "seven_contrasts_packed": True,
            "four_arm_sign_contrast_retains_arm_scores": True,
            "global_token_metadata_readback": True,
            "exact_source_index_schema": True,
            "bf16_archive_hash_verified_readback": True,
            "hard_capacity_guards_pass": True,
        }
        packed = {
            "packed_arrays_bytes": flat_sample["packed_arrays_bytes"],
            "packed_numeric_payload_bytes": flat_sample[
                "packed_numeric_payload_bytes"
            ],
            "packed_row_index_bytes": flat_sample["packed_row_index_bytes"],
            "packed_row_count": flat_sample["packed_row_count"],
            "packed_row_inventory_sha256": (
                benchmark.PACKED_FIXTURE_INVENTORY_SHA256
            ),
            "token_metadata_bytes": flat_sample["token_metadata_bytes"],
            "token_metadata_rows": benchmark.TOKENIZER_SIZE,
            "total_bytes": (
                flat_sample["packed_arrays_bytes"]
                + flat_sample["packed_row_index_bytes"]
                + flat_sample["token_metadata_bytes"]
            ),
            "write_seconds": 0.01,
            "read_seconds": 0.01,
            "packed_arrays_sha256": "1" * 64,
            "packed_row_index_sha256": "2" * 64,
            "token_metadata_sha256": "3" * 64,
        }
        archived_bytes = (
            flat_sample["residual_bytes"]
            + flat_sample["index_bytes"]
            + packed["total_bytes"]
        )
        receipt: dict[str, object] = {
            "schema_version": benchmark.BENCHMARK_SCHEMA_VERSION,
            "status": "pass",
            "study_id": benchmark.STUDY_ID,
            "protocol_version": benchmark.PROTOCOL_VERSION,
            "plan_hash": PLAN_HASH,
            "benchmark_id": "targetblind-benchmark-01",
            "outcome_blind": True,
            "prior_outcome_inputs": [],
            "input_policy": {
                "accepted_inputs": [
                    "pinned local-only public artifacts",
                    "frozen neutral packet embedded in benchmark source",
                    "guarded external volume sentinel",
                    "live B200 price",
                ],
                "plan_hash_binding_input": True,
                "experiment_plan_file_input": False,
                "prefix_bank_input": False,
                "result_input": False,
            },
            "artifact_root_binding": {
                "expected_volume_id": VOLUME_ID,
                "cache_relative_directory": "cache/huggingface",
            },
            "artifacts": {
                "model": {
                    "id": benchmark.MODEL_ID,
                    "revision": benchmark.MODEL_REVISION,
                    "dtype": "bfloat16",
                },
                "sae": {
                    "id": benchmark.SAE_ID,
                    "revision": benchmark.SAE_REVISION,
                    "file_sha256": benchmark.SAE_FILE_SHA256,
                    "runtime_fixture_dtype": "bfloat16",
                },
                "jacobian_lens": {
                    "id": benchmark.JLENS_ID,
                    "revision": benchmark.JLENS_REVISION,
                    "file_sha256": benchmark.JLENS_FILE_SHA256,
                    "runtime_fixture_layer": benchmark.REAL_J_FIXTURE_LAYER,
                    "runtime_fixture_dtype": "bfloat16",
                },
            },
            "runtime": {
                "gpu_name": "NVIDIA B200",
                "gpu_total_memory_bytes": 180 * 1024**3,
                "source_sha256": SOURCE_HASH,
            },
            "neutral_fixture": {
                "neutral_packet_spec_sha256": benchmark.NEUTRAL_PACKET_SPEC_SHA256,
                "trace_states": _trace_labels(),
                "real_j_layer": benchmark.REAL_J_FIXTURE_LAYER,
                "real_j_runtime_dtype": "torch.bfloat16",
                "switch_telemetry": {
                    "call_receipts": [
                        {"selected_positions": 1, "max_abs_delta": 0.01}
                    ]
                },
            },
            "technical_gates": gates,
            "measurements": metrics,
            "archive_sample": {
                "rows": flat_sample["rows"],
                "width": benchmark.MODEL_WIDTH,
                "dtype": "bfloat16",
                "residual_bytes": flat_sample["residual_bytes"],
                "index_bytes": flat_sample["index_bytes"],
                "write_seconds": (
                    archived_bytes / metrics["archive_write_bytes_per_second"]
                ),
                "read_seconds": (
                    archived_bytes / metrics["archive_read_bytes_per_second"]
                ),
                "residual_sha256": "4" * 64,
                "index_sha256": "5" * 64,
                "packed_vocabulary": packed,
            },
            "source_index_contract": {
                "fields": list(benchmark.SOURCE_INDEX_FIELDS),
                "schema_sha256": benchmark.SOURCE_INDEX_SCHEMA_SHA256,
                "representative_rows": 36,
            },
            "exact_max_workload": workload.as_dict(),
            "workload_contract_sha256": benchmark.workload_contract_sha256(workload),
            "capacity_authorization_proposal": capacity,
        }
        cls._rehash(receipt)
        return receipt

    @staticmethod
    def _rehash(receipt: dict[str, object]) -> None:
        receipt.pop("receipt_sha256", None)
        receipt["receipt_sha256"] = hashlib.sha256(
            canonical_json_bytes(receipt)
        ).hexdigest()

    def test_exact_receipt_passes_and_returns_its_binding_hash(self) -> None:
        receipt = self._receipt()
        observed = benchmark.validate_benchmark_receipt(
            receipt,
            expected_plan_hash=PLAN_HASH,
            expected_volume_id=VOLUME_ID,
            expected_prefix_count=160,
            expected_source_sha256=SOURCE_HASH,
        )
        self.assertEqual(observed, receipt["receipt_sha256"])

    def test_rehashed_semantic_tampering_still_fails_closed(self) -> None:
        mutations = (
            ("wrong plan", lambda r: r.__setitem__("plan_hash", "9" * 64)),
            (
                "missing gate",
                lambda r: r["technical_gates"].__setitem__(
                    "chunked_full_vocabulary_logits", False
                ),
            ),
            (
                "wrong model",
                lambda r: r["artifacts"]["model"].__setitem__("revision", "main"),
            ),
            (
                "wrong source schema",
                lambda r: r["source_index_contract"].__setitem__(
                    "representative_rows", 35
                ),
            ),
            (
                "zero edit",
                lambda r: r["neutral_fixture"]["switch_telemetry"][
                    "call_receipts"
                ][0].__setitem__("max_abs_delta", 0.0),
            ),
            (
                "wrong packed rows",
                lambda r: r["archive_sample"]["packed_vocabulary"].__setitem__(
                    "packed_row_count", 27
                ),
            ),
            (
                "invented capacity",
                lambda r: r["capacity_authorization_proposal"].__setitem__(
                    "hard_proposed_gpu_hour_ceiling", 5
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                receipt = copy.deepcopy(self._receipt())
                mutate(receipt)
                self._rehash(receipt)
                with self.assertRaises(benchmark.BenchmarkContractError):
                    benchmark.validate_benchmark_receipt(
                        receipt,
                        expected_plan_hash=PLAN_HASH,
                        expected_volume_id=VOLUME_ID,
                        expected_prefix_count=160,
                        expected_source_sha256=SOURCE_HASH,
                    )

    def test_unrehashed_byte_tampering_fails_canonical_hash(self) -> None:
        receipt = self._receipt()
        receipt["measurements"]["decode_tokens_per_second"] = 201.0
        with self.assertRaisesRegex(
            benchmark.BenchmarkContractError,
            "canonical hash differs",
        ):
            benchmark.validate_benchmark_receipt(
                receipt,
                expected_plan_hash=PLAN_HASH,
                expected_volume_id=VOLUME_ID,
                expected_prefix_count=160,
            )


if __name__ == "__main__":
    unittest.main()
