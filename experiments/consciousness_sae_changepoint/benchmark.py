#!/usr/bin/env python3
"""Outcome-blind B200 capacity benchmark for the changepoint study.

The benchmark is deliberately incapable of accepting an experiment plan,
generated prefix bank, result directory, or prior release as input.  It uses a
locally defined neutral bookkeeping packet and a neutral Yes/No question to
exercise the exact technical primitives needed by the confirmatory runtime:

* pinned local-only BF16 model, SAE, and Jacobian-lens artifact loading;
* manual cached prefill and one-token-at-a-time decoding;
* one nonzero, position-masked layer-50 switch with the complete depth trace;
* a real-J selected-token readout; and
* transactional BF16 safetensors/Parquet write and hash-verified readback.

Only a compact performance receipt is retained.  Sampled neutral text and token
IDs are never written.  A passing receipt is emitted only when the guarded
external volume, hardware, artifact, trace, readout, archive, and budget gates
all pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_changepoint import paths  # noqa: E402
from experiments.consciousness_sae_changepoint.protocol import (  # noqa: E402
    CAPTURE_STATES,
    DIRECT_POSITIONS,
    JLENS_FILENAME,
    JLENS_FILE_SHA256,
    JLENS_ID,
    JLENS_REVISION,
    J_MAP_LAYERS,
    MAIN_POST_EVENT_TOKENS,
    MODEL_ID,
    MODEL_LAYERS,
    MODEL_REVISION,
    MODEL_WIDTH,
    N_PREFIXES,
    PREFIX_TOKENS,
    PROTOCOL_VERSION,
    QUERY_ANSWER_MAX_TOKENS,
    RANDOM_TRANSPORT_SEEDS,
    SAE_FILENAME,
    SAE_FILE_SHA256,
    SAE_ID,
    SAE_LAYER,
    SAE_REVISION,
    SAE_WIDTH,
    STUDY_ID,
    TOKENIZER_SIZE,
    VOCABULARY_CHECKPOINTS,
    VOCABULARY_CONTRASTS,
    VOCABULARY_TOP_K_BY_CHECKPOINT,
    aggregate_blocks,
    canonical_json_bytes,
    fixed_token_rows,
    main_branch_rows,
    prefix_block_assignments,
    prefix_rows,
    probe_templates,
    sampling_domain_hash,
    sha256_file,
)
from experiments.consciousness_sae_changepoint.readouts import (  # noqa: E402
    jlens_normalized_hidden,
    jlens_selected_logits,
    llama_rms_norm,
    selected_lm_head_logits,
)
from experiments.consciousness_sae_changepoint.runtime_core import (  # noqa: E402
    Layer50SwitchHook,
    cache_tensor_sha256,
    extract_hidden_output,
    extract_residual_positions,
    hash_uniform_receipt,
    inverse_cdf_sample,
    tensor_sha256,
)
from experiments.consciousness_sae_changepoint.storage import (  # noqa: E402
    RunTransaction,
    open_source_shard,
)


BENCHMARK_SCHEMA_VERSION = 1
BENCHMARK_PHASE = "benchmark"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# This feature is a fixed capacity-test fixture, not a selected scientific
# feature.  Its label and activation are never queried.  The decoder column is
# normalized to a small but exactly nonzero vector before the one edited call.
NEUTRAL_SAE_FIXTURE_FEATURE_ID = 0
NEUTRAL_SWITCH_VECTOR_L2 = 0.25
REAL_J_FIXTURE_LAYER = 60
JLENS_BENCHMARK_ROWS = 128
JLENS_BENCHMARK_REPEATS = 3
MANUAL_DECODE_STEPS = 8
PROBE_DECODE_STEPS = 8
JUDGE_DECODE_STEPS = 8

# A long neutral packet makes prefill throughput conservative for the shorter
# induction and query suffixes without reading either target string.
NEUTRAL_PREFILL_TARGET_TOKENS = 768
NEUTRAL_PREFILL_MINIMUM_TOKENS = 640
NEUTRAL_PADDING_MAX_REPETITIONS = 256

NEUTRAL_SYSTEM_TEXT = (
    "You are assisting with a deterministic systems-capacity check. Follow the "
    "bookkeeping request literally and keep the answer concise."
)
NEUTRAL_USER_BASE = (
    "A community workshop records ordinary supply movements. Monday begins "
    "with 84 blank cards, receives 26 cards, and uses 19. Tuesday receives 31 "
    "cards and uses 22. Wednesday receives 17 cards and uses 28. Explain the "
    "running balance after each day, then state the final card count."
)
NEUTRAL_PADDING_SENTENCE = (
    " For the capacity record, also note that each labeled tray remains on its "
    "assigned shelf and that no tray is moved between rooms."
)
NEUTRAL_YES_NO_QUERY = (
    "Does the preceding workshop response include at least one numerical "
    "quantity? Begin with Yes or No, then give one short reason."
)
NEUTRAL_JUDGE_SYSTEM = (
    "Return exactly one JSON object with a boolean field named mentions_number."
)
NEUTRAL_JUDGE_USER = (
    "Classify this neutral sentence: 'The workshop counted 84 cards on Monday.'"
)

NEUTRAL_PACKET_SPEC = {
    "schema_version": 1,
    "system": NEUTRAL_SYSTEM_TEXT,
    "user_base": NEUTRAL_USER_BASE,
    "padding_sentence": NEUTRAL_PADDING_SENTENCE,
    "padding_rule": "largest_repeat_count_with_rendered_tokens_at_most_768",
    "query": NEUTRAL_YES_NO_QUERY,
    "judge_system": NEUTRAL_JUDGE_SYSTEM,
    "judge_user": NEUTRAL_JUDGE_USER,
}

# Filled from the canonical source strings, independently asserted in tests.
NEUTRAL_PACKET_SPEC_SHA256 = hashlib.sha256(
    canonical_json_bytes(NEUTRAL_PACKET_SPEC)
).hexdigest()

FAILURE_RESERVE_FACTOR = 1.50
GPU_HOUR_CEILING_QUANTUM = 5
STORAGE_CEILING_QUANTUM_GIB = 10
MAX_PROPOSED_GPU_HOURS = 96
MAX_PROPOSED_STORAGE_GIB = 150
MAX_PROPOSED_SPEND_USD = Decimal("600.00")
SOURCE_SHARD_ROWS = 8192
PACKED_VOCAB_SHARD_ROWS = 128
VOCAB_CHUNK_SIZE = 8192
RAW_TOPK_ENTRY_BYTES = 8
PAIR_UNION_ENTRY_BYTES = 24
SIGN_UNION_ENTRY_BYTES = 32

# Exact source-index fields required by the benchmark and confirmatory writer.
# All scientific and replay bindings are row-local; downstream shards must not
# depend on their surrounding directory name to recover identity.
SOURCE_INDEX_FIELDS = (
    "row_id",
    "study_id",
    "protocol_version",
    "plan_hash",
    "run_id",
    "block_id",
    "attempt",
    "prefix_id",
    "prefix_seed",
    "prefix_token_ids_sha256",
    "branch",
    "branch_id",
    "condition_name",
    "condition_sha256",
    "trace_role",
    "forward_id",
    "event_time",
    "capture_position",
    "capture_input_offset",
    "predicts_distribution_after_input_offset",
    "predicted_token_id",
    "layer_state",
    "j_map_layer",
    "state",
    "intervention_role",
    "intervention_sha256",
    "parent_cache_sha256",
    "output_cache_sha256",
    "sampling_domain_hash",
    "paired_stream_id",
    "decode_step",
    "uniform_receipt_sha256",
    "model_revision",
    "tokenizer_revision",
    "sae_file_sha256",
    "jlens_file_sha256",
)
SOURCE_INDEX_SCHEMA_SHA256 = hashlib.sha256(
    canonical_json_bytes(list(SOURCE_INDEX_FIELDS))
).hexdigest()

# Conservative costing limits.  They are not model inputs or scientific
# observations; they only upper-bound how benchmark rates are expanded.
PREFIX_PREFILL_MAX_TOKENS = 512
PROBE_SUFFIX_PREFILL_MAX_TOKENS = 128
FIXED_FORWARD_MAX_TOKENS = 512
JUDGE_CONTEXT_MAX_TOKENS = 768
JUDGE_OUTPUT_MAX_TOKENS = 64
LOCAL_JUDGE_RETRY_ATTEMPTS = 2


class BenchmarkContractError(RuntimeError):
    """Raised when a target-blind benchmark gate cannot be proven."""


@dataclass(frozen=True)
class ExactWorkload:
    """Protocol-expanded maximum workload before operational reserve."""

    prefixes: int
    main_branches: int
    disposable_probes: int
    fixed_token_forwards: int
    clean_prefix_sampled_tokens: int
    main_post_event_sampled_tokens_max: int
    binary_answer_sampled_tokens_max: int
    natural_judge_items: int
    binary_judge_items: int
    local_judge_base_items: int
    local_judge_invocations_max: int
    local_judge_output_tokens_max: int
    experiment_prefill_tokens_max: int
    local_judge_prefill_tokens_max: int
    sampled_decode_tokens_including_judge_max: int
    pre_window_positions_per_prefix: int
    main_positions_per_prefix: int
    probe_positions_per_prefix: int
    fixed_positions_per_prefix: int
    source_positions_per_prefix: int
    source_states_per_position: int
    j_source_states_per_position: int
    jlens_source_rows: int
    real_j_readout_rows: int
    identity_readout_rows: int
    random_j_readout_rows: int
    final_source_rows: int
    total_source_rows: int
    source_width: int
    exact_bf16_source_payload_bytes: int
    raw_vocab_rows_k512: int
    raw_vocab_rows_k2000: int
    raw_vocab_rows_total: int
    pair_contrast_rows_k512: int
    pair_contrast_rows_k2000: int
    sign_contrast_rows_k512: int
    sign_contrast_rows_k2000: int
    contrast_rows_total: int
    raw_topk_entries_max: int
    pair_union_entries_max: int
    sign_union_entries_max: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def _expanded_protocol_roles() -> dict[str, Any]:
    """Derive per-prefix execution roles from the current protocol rows."""

    prefix_plan = prefix_rows()
    blocks = aggregate_blocks()
    assignments = prefix_block_assignments(prefix_plan, blocks)
    main_plan = main_branch_rows(assignments, blocks, None)
    probe_plan = probe_templates()
    fixed_plan = fixed_token_rows(assignments, blocks, None, None)
    protocol_n = len(prefix_plan)
    if protocol_n != N_PREFIXES or protocol_n <= 0:
        raise BenchmarkContractError("expanded prefix plan differs from protocol N")
    if len(main_plan) % protocol_n or len(fixed_plan) % protocol_n:
        raise BenchmarkContractError("expanded roles are not balanced by prefix")

    checkpoint_per_prefix = {checkpoint: 0 for checkpoint in VOCABULARY_CHECKPOINTS}
    checkpoint_per_prefix["event0"] = len(main_plan) // protocol_n
    for row in probe_plan:
        checkpoint = row.get("capture_position")
        if checkpoint in checkpoint_per_prefix:
            checkpoint_per_prefix[str(checkpoint)] += 1
    fixed_position_total = sum(len(row["capture_positions"]) for row in fixed_plan)
    if fixed_position_total % protocol_n:
        raise BenchmarkContractError("fixed capture positions are not prefix-balanced")
    for checkpoint in ("fixed_prequery", "fixed_answer"):
        checkpoint_total = sum(
            int(checkpoint in row["capture_positions"]) for row in fixed_plan
        )
        if checkpoint_total % protocol_n:
            raise BenchmarkContractError(f"{checkpoint} is not prefix-balanced")
        checkpoint_per_prefix[checkpoint] = checkpoint_total // protocol_n
    if any(value <= 0 for value in checkpoint_per_prefix.values()):
        raise BenchmarkContractError("a registered vocabulary checkpoint has no rows")

    return {
        "protocol_n": protocol_n,
        "main_per_prefix": len(main_plan) // protocol_n,
        "probe_per_prefix": len(probe_plan),
        "fixed_per_prefix": len(fixed_plan) // protocol_n,
        "main_tokens_per_prefix": sum(
            int(row["post_event_max_tokens"]) for row in main_plan
        )
        // protocol_n,
        "probe_answer_tokens_per_prefix": sum(
            int(row["answer_max_tokens"]) for row in probe_plan
        ),
        "fixed_positions_per_prefix": fixed_position_total // protocol_n,
        "checkpoint_positions_per_prefix": checkpoint_per_prefix,
    }


def build_exact_workload(prefix_count: int | None = None) -> ExactWorkload:
    """Scale protocol-derived per-prefix roles to a prospectively selected N."""

    roles = _expanded_protocol_roles()
    prefixes = int(roles["protocol_n"]) if prefix_count is None else prefix_count
    if isinstance(prefixes, bool) or not isinstance(prefixes, int) or prefixes <= 0:
        raise BenchmarkContractError("prefix_count must be a positive integer")
    main_branches = prefixes * int(roles["main_per_prefix"])
    probes = prefixes * int(roles["probe_per_prefix"])
    fixed_forwards = prefixes * int(roles["fixed_per_prefix"])
    prefix_sampled = prefixes * PREFIX_TOKENS
    main_sampled = prefixes * int(roles["main_tokens_per_prefix"])
    binary_sampled = prefixes * int(roles["probe_answer_tokens_per_prefix"])
    natural_judge = main_branches * 2
    binary_judge = probes
    judge_base = natural_judge + binary_judge
    judge_invocations = judge_base * LOCAL_JUDGE_RETRY_ATTEMPTS
    judge_output_tokens = judge_invocations * JUDGE_OUTPUT_MAX_TOKENS
    experiment_prefill = (
        prefixes * PREFIX_PREFILL_MAX_TOKENS
        + probes * PROBE_SUFFIX_PREFILL_MAX_TOKENS
    )
    judge_prefill = judge_invocations * JUDGE_CONTEXT_MAX_TOKENS
    decode_total = prefix_sampled + main_sampled + binary_sampled + judge_output_tokens

    pre_positions = PREFIX_TOKENS - MAIN_POST_EVENT_TOKENS
    main_positions = int(roles["main_tokens_per_prefix"])
    probe_positions = int(roles["probe_per_prefix"])
    fixed_positions = int(roles["fixed_positions_per_prefix"])
    source_positions = pre_positions + main_positions + probe_positions + fixed_positions
    source_states = len(CAPTURE_STATES) + 1
    j_states = len(CAPTURE_STATES)
    j_rows = prefixes * source_positions * j_states
    final_rows = prefixes * source_positions
    total_rows = j_rows + final_rows

    raw_rows_by_k: Counter[int] = Counter()
    pair_rows_by_k: Counter[int] = Counter()
    sign_rows_by_k: Counter[int] = Counter()
    checkpoint_per_prefix = roles["checkpoint_positions_per_prefix"]
    for checkpoint in VOCABULARY_CHECKPOINTS:
        k = int(VOCABULARY_TOP_K_BY_CHECKPOINT[checkpoint])
        raw_rows_by_k[k] += (
            prefixes * int(checkpoint_per_prefix[checkpoint]) * j_states
        )
        # Fixed literal and calibrated rows form two prespecified dose strata.
        strata = 2 if checkpoint.startswith("fixed_") else 1
        pair_rows_by_k[k] += (
            prefixes * j_states * strata * (len(VOCABULARY_CONTRASTS) - 1)
        )
        sign_rows_by_k[k] += prefixes * j_states * strata
    direct_j_rows = sum(
        prefixes * int(checkpoint_per_prefix[checkpoint]) * j_states
        for checkpoint in DIRECT_POSITIONS
    )
    raw_k512 = raw_rows_by_k[512]
    raw_k2000 = raw_rows_by_k[2000]
    pair_k512 = pair_rows_by_k[512]
    pair_k2000 = pair_rows_by_k[2000]
    sign_k512 = sign_rows_by_k[512]
    sign_k2000 = sign_rows_by_k[2000]

    workload = ExactWorkload(
        prefixes=prefixes,
        main_branches=main_branches,
        disposable_probes=probes,
        fixed_token_forwards=fixed_forwards,
        clean_prefix_sampled_tokens=prefix_sampled,
        main_post_event_sampled_tokens_max=main_sampled,
        binary_answer_sampled_tokens_max=binary_sampled,
        natural_judge_items=natural_judge,
        binary_judge_items=binary_judge,
        local_judge_base_items=judge_base,
        local_judge_invocations_max=judge_invocations,
        local_judge_output_tokens_max=judge_output_tokens,
        experiment_prefill_tokens_max=experiment_prefill,
        local_judge_prefill_tokens_max=judge_prefill,
        sampled_decode_tokens_including_judge_max=decode_total,
        pre_window_positions_per_prefix=pre_positions,
        main_positions_per_prefix=main_positions,
        probe_positions_per_prefix=probe_positions,
        fixed_positions_per_prefix=fixed_positions,
        source_positions_per_prefix=source_positions,
        source_states_per_position=source_states,
        j_source_states_per_position=j_states,
        jlens_source_rows=j_rows,
        real_j_readout_rows=j_rows,
        identity_readout_rows=j_rows,
        random_j_readout_rows=direct_j_rows * len(RANDOM_TRANSPORT_SEEDS),
        final_source_rows=final_rows,
        total_source_rows=total_rows,
        source_width=MODEL_WIDTH,
        exact_bf16_source_payload_bytes=total_rows * MODEL_WIDTH * 2,
        raw_vocab_rows_k512=raw_k512,
        raw_vocab_rows_k2000=raw_k2000,
        raw_vocab_rows_total=raw_k512 + raw_k2000,
        pair_contrast_rows_k512=pair_k512,
        pair_contrast_rows_k2000=pair_k2000,
        sign_contrast_rows_k512=sign_k512,
        sign_contrast_rows_k2000=sign_k2000,
        contrast_rows_total=pair_k512 + pair_k2000 + sign_k512 + sign_k2000,
        raw_topk_entries_max=raw_k512 * 512 + raw_k2000 * 2000,
        pair_union_entries_max=pair_k512 * 1024 + pair_k2000 * 4000,
        sign_union_entries_max=sign_k512 * 1024 + sign_k2000 * 4000,
    )
    _validate_exact_workload(workload)
    return workload


def _validate_exact_workload(workload: ExactWorkload) -> None:
    per_prefix = {
        "main_branches": 8,
        "disposable_probes": 41,
        "fixed_token_forwards": 13,
        "jlens_source_rows": 611 * 35,
        "real_j_readout_rows": 611 * 35,
        "identity_readout_rows": 611 * 35,
        "random_j_readout_rows": 7_700,
        "final_source_rows": 611,
        "total_source_rows": 611 * 36,
        "raw_vocab_rows_k512": 1_050,
        "raw_vocab_rows_k2000": 1_540,
        "pair_contrast_rows_k512": 630,
        "pair_contrast_rows_k2000": 1_260,
        "sign_contrast_rows_k512": 105,
        "sign_contrast_rows_k2000": 210,
    }
    for key, expected_per_prefix in per_prefix.items():
        if getattr(workload, key) != expected_per_prefix * workload.prefixes:
            raise BenchmarkContractError(f"exact workload role differs: {key}")
    if (
        workload.pre_window_positions_per_prefix != 32
        or workload.main_positions_per_prefix != 512
        or workload.probe_positions_per_prefix != 41
        or workload.fixed_positions_per_prefix != 26
        or workload.source_positions_per_prefix != 611
        or workload.source_states_per_position != 36
        or workload.j_source_states_per_position != 35
    ):
        raise BenchmarkContractError("source-position allocation differs")
    if workload.exact_bf16_source_payload_bytes != (
        workload.total_source_rows * MODEL_WIDTH * 2
    ):
        raise BenchmarkContractError("exact BF16 source payload differs")


def _positive_rate(metrics: Mapping[str, Any], key: str) -> float:
    value = metrics.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BenchmarkContractError(f"benchmark metric {key!r} is not numeric")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise BenchmarkContractError(f"benchmark metric {key!r} is not positive")
    return value


def validate_source_index_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the exact row-local replay schema shared with the target run."""

    if set(row) != set(SOURCE_INDEX_FIELDS):
        missing = sorted(set(SOURCE_INDEX_FIELDS) - set(row))
        extra = sorted(set(row) - set(SOURCE_INDEX_FIELDS))
        raise BenchmarkContractError(
            f"source-index fields differ; missing={missing}, extra={extra}"
        )
    normalized = dict(row)
    hash_fields = (
        "plan_hash",
        "prefix_token_ids_sha256",
        "condition_sha256",
        "intervention_sha256",
        "parent_cache_sha256",
        "output_cache_sha256",
        "sampling_domain_hash",
        "uniform_receipt_sha256",
        "sae_file_sha256",
        "jlens_file_sha256",
    )
    for field in hash_fields:
        if not isinstance(normalized[field], str) or not HEX64.fullmatch(
            normalized[field]
        ):
            raise BenchmarkContractError(f"source-index {field} is not SHA-256")
    text_fields = (
        "row_id",
        "run_id",
        "block_id",
        "prefix_id",
        "branch",
        "branch_id",
        "condition_name",
        "trace_role",
        "forward_id",
        "capture_position",
        "layer_state",
        "state",
        "intervention_role",
        "paired_stream_id",
    )
    for field in text_fields:
        if not isinstance(normalized[field], str) or not normalized[field]:
            raise BenchmarkContractError(f"source-index {field} must be nonempty text")
    if not re.fullmatch(r"[0-9a-f]{32}", normalized["row_id"]):
        raise BenchmarkContractError("source-index row_id is not 128-bit hex")
    integer_fields = (
        "attempt",
        "prefix_seed",
        "capture_input_offset",
        "predicts_distribution_after_input_offset",
        "predicted_token_id",
        "decode_step",
    )
    for field in integer_fields:
        if isinstance(normalized[field], bool) or not isinstance(normalized[field], int):
            raise BenchmarkContractError(f"source-index {field} must be an integer")
    if any(
        normalized[field] < 0
        for field in (
            "attempt",
            "prefix_seed",
            "capture_input_offset",
            "predicts_distribution_after_input_offset",
            "decode_step",
        )
    ):
        raise BenchmarkContractError("source-index integer coordinate is negative")
    if not 0 <= normalized["predicted_token_id"] < TOKENIZER_SIZE:
        raise BenchmarkContractError("source-index predicted token is out of range")
    if not isinstance(normalized["event_time"], (int, str)) or isinstance(
        normalized["event_time"], bool
    ):
        raise BenchmarkContractError("source-index event_time has an invalid type")
    if normalized["study_id"] != STUDY_ID or normalized[
        "protocol_version"
    ] != PROTOCOL_VERSION:
        raise BenchmarkContractError("source-index study/protocol binding differs")
    if normalized["model_revision"] != MODEL_REVISION or normalized[
        "tokenizer_revision"
    ] != MODEL_REVISION:
        raise BenchmarkContractError("source-index model/tokenizer revision differs")
    if normalized["sae_file_sha256"] != SAE_FILE_SHA256 or normalized[
        "jlens_file_sha256"
    ] != JLENS_FILE_SHA256:
        raise BenchmarkContractError("source-index artifact hashes differ")
    state = normalized["state"]
    layer_state = normalized["layer_state"]
    j_map_layer = normalized["j_map_layer"]
    if state == "final_pre_norm":
        if j_map_layer is not None or layer_state != "final":
            raise BenchmarkContractError("final source layer/J binding differs")
    else:
        if isinstance(j_map_layer, bool) or j_map_layer not in J_MAP_LAYERS:
            raise BenchmarkContractError("non-final source lacks a registered J map")
        expected = {
            "pre_edit": "50_pre",
            "post_edit": "50_post",
            "post_block": str(j_map_layer),
        }.get(state)
        if expected is None or layer_state != expected:
            raise BenchmarkContractError("source-index layer/state binding differs")
    return normalized


def build_representative_source_index_rows(
    labels: Sequence[str],
    *,
    plan_hash: str,
    run_id: str,
    prefix_token_ids_sha256: str,
    predicted_token_id: int,
    intervention_sha256: str,
    parent_cache_sha256: str,
    output_cache_sha256: str,
) -> list[dict[str, Any]]:
    """Build one exact neutral event0 row for every captured source state."""

    for value, label in (
        (plan_hash, "plan_hash"),
        (prefix_token_ids_sha256, "prefix_token_ids_sha256"),
        (intervention_sha256, "intervention_sha256"),
        (parent_cache_sha256, "parent_cache_sha256"),
        (output_cache_sha256, "output_cache_sha256"),
    ):
        if not isinstance(value, str) or not HEX64.fullmatch(value):
            raise BenchmarkContractError(f"{label} is not a SHA-256 value")
    if not isinstance(run_id, str) or not run_id:
        raise BenchmarkContractError("run_id must be nonempty")
    uniform = hash_uniform_receipt(
        sampling_domain_hash=sampling_domain_hash(),
        prefix_seed=2_026_071_398,
        paired_stream_id="neutral-main-benchmark",
        decode_step=2,
    )
    uniform_hash = hashlib.sha256(
        canonical_json_bytes(uniform.as_dict())
    ).hexdigest()
    condition_hash = hashlib.sha256(
        canonical_json_bytes(
            {
                "condition_name": "neutral_nonzero_fixture",
                "intervention_role": "neutral_sae_fixture",
                "feature_id": NEUTRAL_SAE_FIXTURE_FEATURE_ID,
                "vector_l2": NEUTRAL_SWITCH_VECTOR_L2,
            }
        )
    ).hexdigest()
    rows: list[dict[str, Any]] = []
    for index, label in enumerate(labels):
        if label == "50_pre":
            layer_state, j_layer, state = "50_pre", 50, "pre_edit"
        elif label == "50_post":
            layer_state, j_layer, state = "50_post", 50, "post_edit"
        elif label == "final_pre_norm":
            layer_state, j_layer, state = "final", None, "final_pre_norm"
        elif label.endswith("_post") and label[:-5].isdigit():
            j_layer = int(label[:-5])
            layer_state, state = str(j_layer), "post_block"
        else:
            raise BenchmarkContractError(f"unknown representative state {label!r}")
        row = {
            "row_id": hashlib.sha256(
                canonical_json_bytes([run_id, "neutral-source", label])
            ).hexdigest()[:32],
            "study_id": STUDY_ID,
            "protocol_version": PROTOCOL_VERSION,
            "plan_hash": plan_hash,
            "run_id": run_id,
            "block_id": "neutral-bf16-archive",
            "attempt": 0,
            "prefix_id": "neutral-prefix-fixture",
            "prefix_seed": 2_026_071_398,
            "prefix_token_ids_sha256": prefix_token_ids_sha256,
            "branch": "neutral_fixture",
            "branch_id": "neutral-nonzero-layer50-branch",
            "condition_name": "neutral_nonzero_fixture",
            "condition_sha256": condition_hash,
            "trace_role": "event0_capacity_fixture",
            "forward_id": "neutral-nonzero-layer50-call",
            "event_time": 0,
            "capture_position": "event0",
            "capture_input_offset": 0,
            "predicts_distribution_after_input_offset": 0,
            "predicted_token_id": int(predicted_token_id),
            "layer_state": layer_state,
            "j_map_layer": j_layer,
            "state": state,
            "intervention_role": "neutral_sae_fixture",
            "intervention_sha256": intervention_sha256,
            "parent_cache_sha256": parent_cache_sha256,
            "output_cache_sha256": output_cache_sha256,
            "sampling_domain_hash": sampling_domain_hash(),
            "paired_stream_id": "neutral-main-benchmark",
            "decode_step": 2,
            "uniform_receipt_sha256": uniform_hash,
            "model_revision": MODEL_REVISION,
            "tokenizer_revision": MODEL_REVISION,
            "sae_file_sha256": SAE_FILE_SHA256,
            "jlens_file_sha256": JLENS_FILE_SHA256,
        }
        rows.append(validate_source_index_row(row))
    if len(rows) != 36 or len({row["row_id"] for row in rows}) != 36:
        raise BenchmarkContractError("representative source-index rows are incomplete")
    return rows


def estimate_archive_bytes(
    workload: ExactWorkload,
    *,
    sample_rows: int,
    sample_residual_bytes: int,
    sample_index_bytes: int,
    packed_arrays_bytes: int,
    packed_numeric_payload_bytes: int,
    packed_row_index_bytes: int,
    packed_row_count: int,
    token_metadata_bytes: int,
) -> dict[str, int]:
    """Expand measured source, packed-array, index, and token-table bytes."""

    for label, value in (
        ("sample_rows", sample_rows),
        ("sample_residual_bytes", sample_residual_bytes),
        ("sample_index_bytes", sample_index_bytes),
        ("packed_arrays_bytes", packed_arrays_bytes),
        ("packed_numeric_payload_bytes", packed_numeric_payload_bytes),
        ("packed_row_index_bytes", packed_row_index_bytes),
        ("packed_row_count", packed_row_count),
        ("token_metadata_bytes", token_metadata_bytes),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise BenchmarkContractError(f"{label} must be a positive integer")
    sample_raw = sample_rows * workload.source_width * 2
    if sample_residual_bytes < sample_raw:
        raise BenchmarkContractError("sample residual file is smaller than its BF16 payload")
    if packed_arrays_bytes < packed_numeric_payload_bytes:
        raise BenchmarkContractError(
            "sample packed file is smaller than its numeric payload"
        )
    residual_header = sample_residual_bytes - sample_raw
    source_index_bytes_per_row = math.ceil(sample_index_bytes / sample_rows)
    source_shard_count = math.ceil(workload.total_source_rows / SOURCE_SHARD_ROWS)
    source_residual_bytes = (
        workload.exact_bf16_source_payload_bytes
        + source_shard_count * residual_header
    )
    source_index_bytes = workload.total_source_rows * source_index_bytes_per_row

    measured_packed_overhead = packed_arrays_bytes - packed_numeric_payload_bytes
    packed_overhead_bytes_per_row = math.ceil(
        measured_packed_overhead / packed_row_count
    )
    packed_logical_rows = workload.raw_vocab_rows_total + workload.contrast_rows_total
    packed_shard_count = math.ceil(packed_logical_rows / PACKED_VOCAB_SHARD_ROWS)
    packed_numeric_bytes = (
        workload.raw_topk_entries_max * RAW_TOPK_ENTRY_BYTES
        + workload.pair_union_entries_max * PAIR_UNION_ENTRY_BYTES
        + workload.sign_union_entries_max * SIGN_UNION_ENTRY_BYTES
    )
    # A safetensors header has one entry per stored numeric array.  The neutral
    # fixture contains the same raw/pair/sign row kinds as the target archive,
    # so its measured per-logical-row header cost is a safer expansion than
    # treating the smaller fixture header as a fixed cost for a 128-row shard.
    projected_packed_overhead = (
        packed_logical_rows * packed_overhead_bytes_per_row
    )
    packed_array_bytes = packed_numeric_bytes + projected_packed_overhead
    packed_index_bytes_per_row = math.ceil(
        packed_row_index_bytes / packed_row_count
    )
    projected_packed_index_bytes = packed_logical_rows * packed_index_bytes_per_row
    estimated = (
        source_residual_bytes
        + source_index_bytes
        + packed_array_bytes
        + projected_packed_index_bytes
        + token_metadata_bytes
    )
    return {
        "source_shard_rows": SOURCE_SHARD_ROWS,
        "estimated_source_shards": source_shard_count,
        "sample_residual_header_bytes": residual_header,
        "source_index_bytes_per_row": source_index_bytes_per_row,
        "exact_bf16_source_payload_bytes": workload.exact_bf16_source_payload_bytes,
        "projected_source_residual_file_bytes": source_residual_bytes,
        "projected_source_index_bytes": source_index_bytes,
        "packed_vocab_shard_rows": PACKED_VOCAB_SHARD_ROWS,
        "packed_vocab_logical_rows": packed_logical_rows,
        "estimated_packed_vocab_shards": packed_shard_count,
        "sample_packed_safetensors_overhead_bytes": measured_packed_overhead,
        "packed_safetensors_overhead_bytes_per_row": packed_overhead_bytes_per_row,
        "projected_packed_safetensors_overhead_bytes": projected_packed_overhead,
        "exact_packed_numeric_payload_bytes": packed_numeric_bytes,
        "projected_packed_array_file_bytes": packed_array_bytes,
        "packed_row_index_bytes_per_row": packed_index_bytes_per_row,
        "projected_packed_row_index_bytes": projected_packed_index_bytes,
        "measured_global_token_metadata_bytes": token_metadata_bytes,
        "estimated_archive_bytes_before_failure_reserve": estimated,
    }


def extrapolate_capacity(
    metrics: Mapping[str, Any],
    archive_sample: Mapping[str, int],
    *,
    gpu_hourly_usd: Decimal | str | float,
    workload: ExactWorkload | None = None,
) -> dict[str, Any]:
    """Convert measured rates into reserved hard ceilings or fail closed."""

    workload = workload or build_exact_workload()
    load_seconds = _positive_rate(metrics, "model_load_seconds")
    prefill_rate = _positive_rate(metrics, "prefill_tokens_per_second")
    decode_rate = _positive_rate(metrics, "decode_tokens_per_second")
    fixed_rate = _positive_rate(metrics, "fixed_forwards_per_second")
    real_j_rate = _positive_rate(metrics, "real_j_states_per_second")
    identity_rate = _positive_rate(metrics, "identity_states_per_second")
    full_vocab_rate = _positive_rate(metrics, "full_vocab_rows_per_second")
    raw_k512_rate = _positive_rate(metrics, "raw_topk_k512_rows_per_second")
    raw_k2000_rate = _positive_rate(metrics, "raw_topk_k2000_rows_per_second")
    pair_k512_rate = _positive_rate(metrics, "pair_union_k512_rows_per_second")
    pair_k2000_rate = _positive_rate(metrics, "pair_union_k2000_rows_per_second")
    sign_k512_rate = _positive_rate(metrics, "sign_union_k512_rows_per_second")
    sign_k2000_rate = _positive_rate(metrics, "sign_union_k2000_rows_per_second")
    write_rate = _positive_rate(metrics, "archive_write_bytes_per_second")
    read_rate = _positive_rate(metrics, "archive_read_bytes_per_second")

    archive = estimate_archive_bytes(
        workload,
        sample_rows=int(archive_sample["rows"]),
        sample_residual_bytes=int(archive_sample["residual_bytes"]),
        sample_index_bytes=int(archive_sample["index_bytes"]),
        packed_arrays_bytes=int(archive_sample["packed_arrays_bytes"]),
        packed_numeric_payload_bytes=int(
            archive_sample["packed_numeric_payload_bytes"]
        ),
        packed_row_index_bytes=int(archive_sample["packed_row_index_bytes"]),
        packed_row_count=int(archive_sample["packed_row_count"]),
        token_metadata_bytes=int(archive_sample["token_metadata_bytes"]),
    )
    archive_bytes = archive["estimated_archive_bytes_before_failure_reserve"]
    component_seconds = {
        "model_load": load_seconds,
        "experiment_and_judge_prefill": (
            workload.experiment_prefill_tokens_max
            + workload.local_judge_prefill_tokens_max
        )
        / prefill_rate,
        "sampled_decode_including_max_judge_retry": (
            workload.sampled_decode_tokens_including_judge_max / decode_rate
        ),
        "fixed_token_forwards": workload.fixed_token_forwards / fixed_rate,
        "real_j_full_trace_selected_readouts": workload.real_j_readout_rows
        / real_j_rate,
        "identity_full_trace_selected_readouts": workload.identity_readout_rows
        / identity_rate,
        "five_random_j_direct_checkpoint_readouts": workload.random_j_readout_rows
        / real_j_rate,
        "checkpoint_full_vocabulary_lm_head": workload.raw_vocab_rows_total
        / full_vocab_rate,
        "raw_topk_k512_packing": workload.raw_vocab_rows_k512 / raw_k512_rate,
        "raw_topk_k2000_packing": workload.raw_vocab_rows_k2000 / raw_k2000_rate,
        "pair_delta_union_k512_packing": workload.pair_contrast_rows_k512
        / pair_k512_rate,
        "pair_delta_union_k2000_packing": workload.pair_contrast_rows_k2000
        / pair_k2000_rate,
        "four_arm_sign_union_k512_packing": workload.sign_contrast_rows_k512
        / sign_k512_rate,
        "four_arm_sign_union_k2000_packing": workload.sign_contrast_rows_k2000
        / sign_k2000_rate,
        "archive_write_and_readback": archive_bytes / write_rate + archive_bytes / read_rate,
    }
    raw_seconds = sum(component_seconds.values())
    reserved_seconds = raw_seconds * FAILURE_RESERVE_FACTOR
    reserved_hours = reserved_seconds / 3600.0
    proposed_gpu_hours = max(
        GPU_HOUR_CEILING_QUANTUM,
        math.ceil(reserved_hours / GPU_HOUR_CEILING_QUANTUM)
        * GPU_HOUR_CEILING_QUANTUM,
    )

    reserved_storage_bytes = math.ceil(archive_bytes * FAILURE_RESERVE_FACTOR)
    gib = 1024**3
    proposed_storage_gib = max(
        STORAGE_CEILING_QUANTUM_GIB,
        math.ceil(
            reserved_storage_bytes
            / gib
            / STORAGE_CEILING_QUANTUM_GIB
        )
        * STORAGE_CEILING_QUANTUM_GIB,
    )

    try:
        hourly = Decimal(str(gpu_hourly_usd))
    except Exception as exc:  # pragma: no cover - defensive Decimal surface
        raise BenchmarkContractError("GPU hourly rate is not decimal-compatible") from exc
    if not hourly.is_finite() or hourly <= 0:
        raise BenchmarkContractError("GPU hourly rate must be finite and positive")
    proposed_spend = (
        hourly * Decimal(proposed_gpu_hours)
    ).quantize(Decimal("0.01"), rounding=ROUND_CEILING)

    failures: list[str] = []
    if proposed_gpu_hours > MAX_PROPOSED_GPU_HOURS:
        failures.append(
            f"GPU-hour proposal {proposed_gpu_hours} exceeds {MAX_PROPOSED_GPU_HOURS}"
        )
    if proposed_storage_gib > MAX_PROPOSED_STORAGE_GIB:
        failures.append(
            f"storage proposal {proposed_storage_gib} GiB exceeds "
            f"{MAX_PROPOSED_STORAGE_GIB} GiB"
        )
    if proposed_spend > MAX_PROPOSED_SPEND_USD:
        failures.append(
            f"spend proposal ${proposed_spend} exceeds ${MAX_PROPOSED_SPEND_USD}"
        )
    if failures:
        raise BenchmarkContractError("; ".join(failures))

    return {
        "method": "measured_target_blind_max_workload_v1",
        "failure_reserve_factor": FAILURE_RESERVE_FACTOR,
        "component_seconds_before_failure_reserve": component_seconds,
        "estimated_gpu_seconds_before_failure_reserve": raw_seconds,
        "estimated_gpu_hours_before_failure_reserve": raw_seconds / 3600.0,
        "estimated_gpu_hours_with_failure_reserve": reserved_hours,
        "hard_proposed_gpu_hour_ceiling": proposed_gpu_hours,
        "live_gpu_hourly_rate_usd": str(hourly),
        "hard_proposed_spend_ceiling_usd": str(proposed_spend),
        "absolute_gpu_hour_guard": MAX_PROPOSED_GPU_HOURS,
        "absolute_spend_guard_usd": str(MAX_PROPOSED_SPEND_USD),
        "archive_projection": archive,
        "archive_bytes_with_failure_reserve": reserved_storage_bytes,
        "hard_proposed_storage_ceiling_gib": proposed_storage_gib,
        "absolute_storage_guard_gib": MAX_PROPOSED_STORAGE_GIB,
    }


def workload_contract_sha256(workload: ExactWorkload) -> str:
    return hashlib.sha256(canonical_json_bytes(workload.as_dict())).hexdigest()


def _receipt_mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise BenchmarkContractError(f"benchmark receipt {key!r} is not an object")
    return value


def validate_benchmark_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_plan_hash: str,
    expected_volume_id: str,
    expected_prefix_count: int,
    expected_source_sha256: str | None = None,
) -> str:
    """Validate a passing benchmark for exact machine-plan gate binding."""

    if not isinstance(expected_plan_hash, str) or not HEX64.fullmatch(
        expected_plan_hash
    ):
        raise BenchmarkContractError("expected plan hash is not SHA-256")
    if not isinstance(expected_volume_id, str) or not expected_volume_id:
        raise BenchmarkContractError("expected volume ID is empty")
    observed_hash = receipt.get("receipt_sha256")
    if not isinstance(observed_hash, str) or not HEX64.fullmatch(observed_hash):
        raise BenchmarkContractError("benchmark receipt hash is missing")
    payload = dict(receipt)
    payload.pop("receipt_sha256", None)
    if hashlib.sha256(canonical_json_bytes(payload)).hexdigest() != observed_hash:
        raise BenchmarkContractError("benchmark receipt canonical hash differs")
    if receipt.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        raise BenchmarkContractError("benchmark receipt schema differs")
    if receipt.get("status") != "pass" or receipt.get("study_id") != STUDY_ID:
        raise BenchmarkContractError("benchmark receipt does not pass for this study")
    if receipt.get("protocol_version") != PROTOCOL_VERSION:
        raise BenchmarkContractError("benchmark protocol version differs")
    if receipt.get("outcome_blind") is not True or receipt.get(
        "prior_outcome_inputs"
    ) != []:
        raise BenchmarkContractError("benchmark receipt is not outcome-blind")
    if receipt.get("plan_hash") != expected_plan_hash:
        raise BenchmarkContractError("benchmark plan hash differs")
    policy = _receipt_mapping(receipt, "input_policy")
    expected_policy = {
        "plan_hash_binding_input": True,
        "experiment_plan_file_input": False,
        "prefix_bank_input": False,
        "result_input": False,
    }
    if any(policy.get(key) is not value for key, value in expected_policy.items()):
        raise BenchmarkContractError("benchmark accepted-input policy differs")
    accepted_inputs = policy.get("accepted_inputs")
    expected_inputs = [
        "pinned local-only public artifacts",
        "frozen neutral packet embedded in benchmark source",
        "guarded external volume sentinel",
        "live B200 price",
    ]
    if accepted_inputs != expected_inputs:
        raise BenchmarkContractError("benchmark accepted-input inventory differs")
    binding = _receipt_mapping(receipt, "artifact_root_binding")
    if binding.get("expected_volume_id") != expected_volume_id:
        raise BenchmarkContractError("benchmark volume binding differs")
    cache_relative = binding.get("cache_relative_directory")
    if (
        not isinstance(cache_relative, str)
        or not cache_relative
        or cache_relative.startswith("/")
        or ".." in cache_relative.split("/")
    ):
        raise BenchmarkContractError("benchmark cache binding is not relative")
    expected_workload = build_exact_workload(expected_prefix_count)
    if receipt.get("exact_max_workload") != expected_workload.as_dict():
        raise BenchmarkContractError("benchmark exact workload differs")
    if receipt.get("workload_contract_sha256") != workload_contract_sha256(
        expected_workload
    ):
        raise BenchmarkContractError("benchmark workload hash differs")
    source_contract = _receipt_mapping(receipt, "source_index_contract")
    if (
        source_contract.get("fields") != list(SOURCE_INDEX_FIELDS)
        or source_contract.get("schema_sha256") != SOURCE_INDEX_SCHEMA_SHA256
        or source_contract.get("representative_rows") != len(CAPTURE_STATES) + 1
    ):
        raise BenchmarkContractError("benchmark source-index contract differs")
    artifacts = _receipt_mapping(receipt, "artifacts")
    model_artifact = _receipt_mapping(artifacts, "model")
    sae_artifact = _receipt_mapping(artifacts, "sae")
    lens_artifact = _receipt_mapping(artifacts, "jacobian_lens")
    if model_artifact != {
        "id": MODEL_ID,
        "revision": MODEL_REVISION,
        "dtype": "bfloat16",
    }:
        raise BenchmarkContractError("benchmark model artifact binding differs")
    if (
        sae_artifact.get("id") != SAE_ID
        or sae_artifact.get("revision") != SAE_REVISION
        or sae_artifact.get("file_sha256") != SAE_FILE_SHA256
        or sae_artifact.get("runtime_fixture_dtype") != "bfloat16"
    ):
        raise BenchmarkContractError("benchmark SAE artifact binding differs")
    if (
        lens_artifact.get("id") != JLENS_ID
        or lens_artifact.get("revision") != JLENS_REVISION
        or lens_artifact.get("file_sha256") != JLENS_FILE_SHA256
        or lens_artifact.get("runtime_fixture_layer") != REAL_J_FIXTURE_LAYER
        or lens_artifact.get("runtime_fixture_dtype") != "bfloat16"
    ):
        raise BenchmarkContractError("benchmark J-lens artifact binding differs")
    runtime = _receipt_mapping(receipt, "runtime")
    gpu_memory = runtime.get("gpu_total_memory_bytes")
    if (
        "B200" not in str(runtime.get("gpu_name", "")).upper()
        or isinstance(gpu_memory, bool)
        or not isinstance(gpu_memory, int)
        or gpu_memory < 170 * 1024**3
    ):
        raise BenchmarkContractError("benchmark B200 runtime binding differs")
    source_sha = runtime.get("source_sha256")
    if not isinstance(source_sha, str) or not HEX64.fullmatch(source_sha):
        raise BenchmarkContractError("benchmark source hash is missing")
    if expected_source_sha256 is not None and source_sha != expected_source_sha256:
        raise BenchmarkContractError("benchmark source hash differs")
    fixture = _receipt_mapping(receipt, "neutral_fixture")
    expected_trace = [
        *(f"{layer}_post" for layer in range(45, 50)),
        "50_pre",
        "50_post",
        *(f"{layer}_post" for layer in range(51, 79)),
        "final_pre_norm",
    ]
    if (
        fixture.get("neutral_packet_spec_sha256") != NEUTRAL_PACKET_SPEC_SHA256
        or fixture.get("trace_states") != expected_trace
        or fixture.get("real_j_layer") != REAL_J_FIXTURE_LAYER
        or fixture.get("real_j_runtime_dtype") != "torch.bfloat16"
    ):
        raise BenchmarkContractError("benchmark neutral fixture binding differs")
    switch = fixture.get("switch_telemetry")
    calls = switch.get("call_receipts") if isinstance(switch, Mapping) else None
    first_call = (
        calls[0]
        if isinstance(calls, list) and calls and isinstance(calls[0], Mapping)
        else {}
    )
    max_abs_delta = first_call.get("max_abs_delta")
    if (
        not isinstance(calls, list)
        or len(calls) != 1
        or not isinstance(calls[0], Mapping)
        or first_call.get("selected_positions") != 1
        or isinstance(max_abs_delta, bool)
        or not isinstance(max_abs_delta, (int, float))
        or not math.isfinite(float(max_abs_delta))
        or float(max_abs_delta) <= 0
    ):
        raise BenchmarkContractError("benchmark nonzero switch receipt differs")
    gates = _receipt_mapping(receipt, "technical_gates")
    required_gates = {
        "b200_single_gpu",
        "local_only_artifacts",
        "bf16_model_sae_and_real_j",
        "manual_incremental_decode",
        "one_nonzero_masked_layer50_call",
        "trace_45_49_50pre_50post_51_78_final",
        "real_j_selected_readout",
        "identity_full_trace_costed",
        "five_random_j_direct_positions_costed",
        "chunked_full_vocabulary_logits",
        "raw_k512_and_k2000_packed",
        "seven_contrasts_packed",
        "four_arm_sign_contrast_retains_arm_scores",
        "global_token_metadata_readback",
        "exact_source_index_schema",
        "bf16_archive_hash_verified_readback",
        "hard_capacity_guards_pass",
    }
    if not required_gates <= set(gates) or any(
        gates.get(key) is not True for key in required_gates
    ):
        raise BenchmarkContractError("benchmark technical gates are incomplete")
    measurements = _receipt_mapping(receipt, "measurements")
    for key in (
        "model_load_seconds",
        "prefill_tokens_per_second",
        "decode_tokens_per_second",
        "fixed_forwards_per_second",
        "real_j_states_per_second",
        "identity_states_per_second",
        "full_vocab_rows_per_second",
        "raw_topk_k512_rows_per_second",
        "raw_topk_k2000_rows_per_second",
        "pair_union_k512_rows_per_second",
        "pair_union_k2000_rows_per_second",
        "sign_union_k512_rows_per_second",
        "sign_union_k2000_rows_per_second",
        "archive_write_bytes_per_second",
        "archive_read_bytes_per_second",
    ):
        _positive_rate(measurements, key)
    archive_sample = _receipt_mapping(receipt, "archive_sample")
    packed_sample = _receipt_mapping(archive_sample, "packed_vocabulary")
    if (
        archive_sample.get("rows") != len(CAPTURE_STATES) + 1
        or archive_sample.get("width") != MODEL_WIDTH
        or archive_sample.get("dtype") != "bfloat16"
    ):
        raise BenchmarkContractError("benchmark source archive fixture differs")
    for field in ("residual_sha256", "index_sha256"):
        value = archive_sample.get(field)
        if not isinstance(value, str) or not HEX64.fullmatch(value):
            raise BenchmarkContractError(f"benchmark archive {field} is missing")
    for field in (
        "packed_arrays_sha256",
        "packed_row_index_sha256",
        "token_metadata_sha256",
    ):
        value = packed_sample.get(field)
        if not isinstance(value, str) or not HEX64.fullmatch(value):
            raise BenchmarkContractError(f"benchmark packed archive {field} is missing")
    expected_packed_rows = len(VOCABULARY_CHECKPOINTS) * (7 + 6 + 1)
    if (
        packed_sample.get("packed_row_count") != expected_packed_rows
        or packed_sample.get("packed_row_inventory_sha256")
        != PACKED_FIXTURE_INVENTORY_SHA256
        or packed_sample.get("token_metadata_rows") != TOKENIZER_SIZE
    ):
        raise BenchmarkContractError("benchmark packed archive row counts differ")
    packed_total_values: list[int] = []
    for key in (
        "packed_arrays_bytes",
        "packed_row_index_bytes",
        "token_metadata_bytes",
    ):
        value = packed_sample.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise BenchmarkContractError(f"benchmark packed archive {key} is invalid")
        packed_total_values.append(value)
    packed_total = sum(packed_total_values)
    if packed_sample.get("total_bytes") != packed_total:
        raise BenchmarkContractError("benchmark packed archive byte total differs")
    for owner, field in (
        (archive_sample, "write_seconds"),
        (archive_sample, "read_seconds"),
        (packed_sample, "write_seconds"),
        (packed_sample, "read_seconds"),
    ):
        value = owner.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) <= 0
        ):
            raise BenchmarkContractError(f"benchmark archive {field} is invalid")
    flattened_sample = {
        "rows": archive_sample.get("rows"),
        "residual_bytes": archive_sample.get("residual_bytes"),
        "index_bytes": archive_sample.get("index_bytes"),
        "packed_arrays_bytes": packed_sample.get("packed_arrays_bytes"),
        "packed_numeric_payload_bytes": packed_sample.get(
            "packed_numeric_payload_bytes"
        ),
        "packed_row_index_bytes": packed_sample.get("packed_row_index_bytes"),
        "packed_row_count": packed_sample.get("packed_row_count"),
        "token_metadata_bytes": packed_sample.get("token_metadata_bytes"),
    }
    for key, value in flattened_sample.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise BenchmarkContractError(f"benchmark archive sample {key} is invalid")
    archived_bytes = (
        int(flattened_sample["residual_bytes"])
        + int(flattened_sample["index_bytes"])
        + packed_total
    )
    expected_write_rate = archived_bytes / float(archive_sample["write_seconds"])
    expected_read_rate = archived_bytes / float(archive_sample["read_seconds"])
    if not math.isclose(
        float(measurements["archive_write_bytes_per_second"]),
        expected_write_rate,
        rel_tol=1e-12,
    ) or not math.isclose(
        float(measurements["archive_read_bytes_per_second"]),
        expected_read_rate,
        rel_tol=1e-12,
    ):
        raise BenchmarkContractError("benchmark archive rates do not match measured bytes")
    capacity = _receipt_mapping(receipt, "capacity_authorization_proposal")
    hourly = capacity.get("live_gpu_hourly_rate_usd")
    recomputed_capacity = extrapolate_capacity(
        measurements,
        flattened_sample,
        gpu_hourly_usd=str(hourly),
        workload=expected_workload,
    )
    if dict(capacity) != recomputed_capacity:
        raise BenchmarkContractError("benchmark capacity proposal is not reproducible")
    return observed_hash


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sync(torch: Any) -> None:
    torch.cuda.synchronize()


def _timed_cuda(torch: Any, function: Any) -> tuple[Any, float]:
    _sync(torch)
    started = time.perf_counter()
    value = function()
    _sync(torch)
    elapsed = time.perf_counter() - started
    if not math.isfinite(elapsed) or elapsed <= 0:
        raise BenchmarkContractError("CUDA timer did not advance")
    return value, elapsed


def _state_key(state: Mapping[str, Any], suffix: str) -> str:
    matches = [key for key in state if key == suffix or key.endswith("." + suffix)]
    if len(matches) != 1:
        raise BenchmarkContractError(
            f"expected one artifact key ending in {suffix!r}, found {matches}"
        )
    return matches[0]


def _token_ids(tokenized: Any) -> Any:
    if hasattr(tokenized, "input_ids"):
        return tokenized.input_ids
    if isinstance(tokenized, Mapping):
        return tokenized["input_ids"]
    return tokenized


def _rendered_neutral_packet(tokenizer: Any) -> tuple[list[dict[str, str]], Any, int]:
    """Build the largest frozen neutral packet not exceeding 768 tokens."""

    best: tuple[list[dict[str, str]], Any, int] | None = None
    for repetitions in range(NEUTRAL_PADDING_MAX_REPETITIONS + 1):
        content = NEUTRAL_USER_BASE + NEUTRAL_PADDING_SENTENCE * repetitions
        messages = [
            {"role": "system", "content": NEUTRAL_SYSTEM_TEXT},
            {"role": "user", "content": content},
        ]
        ids = _token_ids(
            tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_tensors="pt",
            )
        )
        if ids.ndim != 2 or int(ids.shape[0]) != 1:
            raise BenchmarkContractError("neutral packet tokenization is not [1, seq]")
        length = int(ids.shape[1])
        if length > NEUTRAL_PREFILL_TARGET_TOKENS:
            break
        best = (messages, ids, repetitions)
    if best is None or int(best[1].shape[1]) < NEUTRAL_PREFILL_MINIMUM_TOKENS:
        raise BenchmarkContractError(
            "neutral packet did not reach the frozen conservative prefill length"
        )
    return best


def _single_yes_no_ids(tokenizer: Any) -> tuple[int, int]:
    yes = tokenizer.encode(" Yes", add_special_tokens=False)
    no = tokenizer.encode(" No", add_special_tokens=False)
    if len(yes) != 1 or len(no) != 1 or yes[0] == no[0]:
        raise BenchmarkContractError("neutral Yes/No readout is not two singleton IDs")
    return int(yes[0]), int(no[0])


def _sample_next(logits: Any, *, step: int, stream: str) -> int:
    decision = inverse_cdf_sample(
        logits,
        sampling_domain_hash=sampling_domain_hash(),
        prefix_seed=2_026_071_398,
        paired_stream_id=stream,
        decode_step=step,
        temperature=0.5,
        top_p=1.0,
        top_k=None,
    )
    return int(decision.token_id)


def _trace_hooks(model: Any, trace: dict[str, Any]) -> list[Any]:
    handles: list[Any] = []

    def output_hook(label: str) -> Any:
        def hook(_module: Any, _inputs: Any, output: Any) -> None:
            if label in trace:
                raise BenchmarkContractError(f"trace hook fired twice: {label}")
            trace[label] = extract_residual_positions(
                output, -1, batch_index=0, to_cpu=True
            )

        return hook

    for layer in range(45, 50):
        handles.append(
            model.model.layers[layer].register_forward_hook(
                output_hook(f"{layer}_post")
            )
        )
    for layer in range(51, 79):
        handles.append(
            model.model.layers[layer].register_forward_hook(
                output_hook(f"{layer}_post")
            )
        )

    def final_pre_hook(_module: Any, inputs: Sequence[Any]) -> None:
        if "final_pre_norm" in trace:
            raise BenchmarkContractError("final pre-norm hook fired twice")
        if not inputs:
            raise BenchmarkContractError("final pre-norm hook received no input")
        trace["final_pre_norm"] = extract_residual_positions(
            inputs[0], -1, batch_index=0, to_cpu=True
        )

    handles.append(model.model.norm.register_forward_pre_hook(final_pre_hook))
    return handles


def _remove_handles(handles: Sequence[Any]) -> None:
    for handle in reversed(handles):
        handle.remove()


def _chunked_full_vocab_logits(
    normalized_hidden: Any, lm_head_weight: Any, *, chunk_size: int = VOCAB_CHUNK_SIZE
) -> Any:
    """Compute every vocabulary logit through bounded LM-head column chunks."""

    torch = __import__("torch")
    if normalized_hidden.ndim != 2 or lm_head_weight.ndim != 2:
        raise BenchmarkContractError("full-vocabulary tensors must be matrices")
    if normalized_hidden.shape[1] != lm_head_weight.shape[1]:
        raise BenchmarkContractError("full-vocabulary hidden/head widths differ")
    pieces = []
    for start in range(0, int(lm_head_weight.shape[0]), chunk_size):
        weight = lm_head_weight[start : start + chunk_size]
        pieces.append(
            (normalized_hidden.to(dtype=weight.dtype) @ weight.T).to(torch.float32)
        )
    logits = torch.cat(pieces, dim=1)
    if tuple(logits.shape) != (
        int(normalized_hidden.shape[0]),
        int(lm_head_weight.shape[0]),
    ) or not bool(torch.isfinite(logits).all()):
        raise BenchmarkContractError("chunked full-vocabulary logits are invalid")
    return logits


def _stable_raw_topk(scores: Any, *, k: int) -> dict[str, Any]:
    """Pack highest raw logits, breaking exact ties by lower token ID."""

    torch = __import__("torch")
    if scores.ndim != 2 or not 0 < k <= int(scores.shape[1]):
        raise BenchmarkContractError("raw top-k score shape/K differs")
    order = torch.argsort(scores, dim=1, descending=True, stable=True)[:, :k]
    packed_scores = scores.gather(1, order).to(torch.float32)
    return {
        "token_ids": order.to(torch.int32).contiguous(),
        "scores": packed_scores.contiguous(),
    }


def _tail_union_indices(delta: Any, *, k: int) -> tuple[Any, Any, Any]:
    torch = __import__("torch")
    if delta.ndim != 1 or not 0 < k <= int(delta.numel()):
        raise BenchmarkContractError("contrast delta shape/K differs")
    positive = torch.argsort(delta, descending=True, stable=True)[:k]
    negative = torch.argsort(delta, descending=False, stable=True)[:k]
    union = torch.unique(torch.cat((positive, negative)), sorted=True)
    positive_rank = torch.full(
        (union.numel(),), -1, device=delta.device, dtype=torch.int32
    )
    negative_rank = torch.full_like(positive_rank, -1)
    positions = torch.full(
        (delta.numel(),), -1, device=delta.device, dtype=torch.long
    )
    positions[union] = torch.arange(union.numel(), device=delta.device)
    positive_rank[positions[positive]] = torch.arange(
        1, k + 1, device=delta.device, dtype=torch.int32
    )
    negative_rank[positions[negative]] = torch.arange(
        1, k + 1, device=delta.device, dtype=torch.int32
    )
    return union, positive_rank, negative_rank


def pack_pair_delta_union(left: Any, right: Any, *, k: int) -> dict[str, Any]:
    """Pack two-arm tails with both arm scores and exact ranks."""

    torch = __import__("torch")
    if left.ndim != 1 or right.shape != left.shape:
        raise BenchmarkContractError("paired contrast arm shapes differ")
    delta = left.float() - right.float()
    union, positive_rank, negative_rank = _tail_union_indices(delta, k=k)
    return {
        "token_ids": union.to(torch.int32).contiguous(),
        "left_scores": left[union].to(torch.float32).contiguous(),
        "right_scores": right[union].to(torch.float32).contiguous(),
        "delta": delta[union].to(torch.float32).contiguous(),
        "positive_rank": positive_rank.contiguous(),
        "negative_rank": negative_rank.contiguous(),
    }


def pack_four_arm_sign_union(
    target_supp: Any,
    target_amp: Any,
    matched_supp: Any,
    matched_amp: Any,
    *,
    k: int,
) -> dict[str, Any]:
    """Pack ((target supp-amp) - (matched supp-amp))/2 with all arms."""

    torch = __import__("torch")
    arms = (target_supp, target_amp, matched_supp, matched_amp)
    if any(arm.ndim != 1 or arm.shape != target_supp.shape for arm in arms):
        raise BenchmarkContractError("four-arm sign contrast shapes differ")
    delta = (
        target_supp.float()
        - target_amp.float()
        - matched_supp.float()
        + matched_amp.float()
    ) / 2.0
    union, positive_rank, negative_rank = _tail_union_indices(delta, k=k)
    return {
        "token_ids": union.to(torch.int32).contiguous(),
        "target_supp_scores": target_supp[union].to(torch.float32).contiguous(),
        "target_amp_scores": target_amp[union].to(torch.float32).contiguous(),
        "matched_supp_scores": matched_supp[union].to(torch.float32).contiguous(),
        "matched_amp_scores": matched_amp[union].to(torch.float32).contiguous(),
        "delta": delta[union].to(torch.float32).contiguous(),
        "positive_rank": positive_rank.contiguous(),
        "negative_rank": negative_rank.contiguous(),
    }


def _packed_numeric_bytes(tensors: Mapping[str, Any]) -> int:
    total = 0
    for tensor in tensors.values():
        total += int(tensor.numel()) * int(tensor.element_size())
    return total


def _expected_packed_fixture_rows() -> list[dict[str, Any]]:
    """Return the exact neutral row inventory for all frozen browse roles."""

    arm_names = (
        "never",
        "target_supp",
        "target_amp",
        "matched_supp",
        "matched_amp",
        "isotropic_supp",
        "isotropic_amp",
    )
    rows: list[dict[str, Any]] = []
    for k in (512, 2000):
        checkpoints = [
            checkpoint
            for checkpoint in VOCABULARY_CHECKPOINTS
            if VOCABULARY_TOP_K_BY_CHECKPOINT[checkpoint] == k
        ]
        for checkpoint in checkpoints:
            tensor_prefix = f"raw_{checkpoint}_k{k}"
            for arm_index, arm_name in enumerate(arm_names):
                rows.append(
                    {
                        "packed_row_id": f"raw-{checkpoint}-k{k}-{arm_name}",
                        "row_kind": "raw_topk",
                        "checkpoint": checkpoint,
                        "k": k,
                        "contrast_id": None,
                        "arm_name": arm_name,
                        "tensor_prefix": tensor_prefix,
                        "tensor_row_offset": arm_index,
                    }
                )
            for contrast_id in VOCABULARY_CONTRASTS[:6]:
                safe_id = contrast_id.replace("_minus_never", "")
                tensor_prefix = f"pair_{checkpoint}_k{k}_{safe_id}"
                rows.append(
                    {
                        "packed_row_id": f"pair-{checkpoint}-k{k}-{contrast_id}",
                        "row_kind": "pair_delta_union",
                        "checkpoint": checkpoint,
                        "k": k,
                        "contrast_id": contrast_id,
                        "arm_name": None,
                        "tensor_prefix": tensor_prefix,
                        "tensor_row_offset": 0,
                    }
                )
            tensor_prefix = f"sign_{checkpoint}_k{k}"
            rows.append(
                {
                    "packed_row_id": (
                        f"sign-{checkpoint}-k{k}-{VOCABULARY_CONTRASTS[-1]}"
                    ),
                    "row_kind": "four_arm_sign_union",
                    "checkpoint": checkpoint,
                    "k": k,
                    "contrast_id": VOCABULARY_CONTRASTS[-1],
                    "arm_name": None,
                    "tensor_prefix": tensor_prefix,
                    "tensor_row_offset": 0,
                }
            )
    return rows


PACKED_FIXTURE_INVENTORY_SHA256 = hashlib.sha256(
    canonical_json_bytes(_expected_packed_fixture_rows())
).hexdigest()


def _load_artifacts(cache_dir: Path) -> dict[str, Any]:
    import torch
    from huggingface_hub import hf_hub_download, snapshot_download
    from transformers import AutoModelForCausalLM, AutoTokenizer

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    snapshot = Path(
        snapshot_download(
            repo_id=MODEL_ID,
            revision=MODEL_REVISION,
            cache_dir=cache_dir,
            token=token,
            local_files_only=True,
        )
    )
    sae_path = Path(
        hf_hub_download(
            repo_id=SAE_ID,
            filename=SAE_FILENAME,
            revision=SAE_REVISION,
            cache_dir=cache_dir,
            token=token,
            local_files_only=True,
        )
    )
    lens_path = Path(
        hf_hub_download(
            repo_id=JLENS_ID,
            filename=JLENS_FILENAME,
            revision=JLENS_REVISION,
            cache_dir=cache_dir,
            token=token,
            local_files_only=True,
        )
    )
    if snapshot.name != MODEL_REVISION:
        raise BenchmarkContractError("local model snapshot does not resolve to the pin")
    if sha256_file(sae_path) != SAE_FILE_SHA256:
        raise BenchmarkContractError("SAE file hash differs from the pin")
    if sha256_file(lens_path) != JLENS_FILE_SHA256:
        raise BenchmarkContractError("J-lens file hash differs from the pin")

    tokenizer = AutoTokenizer.from_pretrained(
        snapshot,
        local_files_only=True,
        trust_remote_code=False,
        token=token,
        use_fast=True,
    )
    if len(tokenizer) != TOKENIZER_SIZE:
        raise BenchmarkContractError("tokenizer length differs from the pin")

    torch.cuda.reset_peak_memory_stats()
    _sync(torch)
    load_started = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(
        snapshot,
        local_files_only=True,
        trust_remote_code=False,
        token=token,
        dtype=torch.bfloat16,
        device_map={"": 0},
        low_cpu_mem_usage=True,
        attn_implementation="sdpa",
    )
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    _sync(torch)
    model_load_seconds = time.perf_counter() - load_started
    config = model.config.get_text_config()
    if (
        int(config.hidden_size) != MODEL_WIDTH
        or int(config.num_hidden_layers) != MODEL_LAYERS
        or len(model.model.layers) != MODEL_LAYERS
        or tuple(model.lm_head.weight.shape) != (TOKENIZER_SIZE, MODEL_WIDTH)
    ):
        raise BenchmarkContractError("live model architecture differs from the pin")
    if next(model.parameters()).dtype != torch.bfloat16:
        raise BenchmarkContractError("live model is not BF16")
    model_load_peak = int(torch.cuda.max_memory_allocated())

    sae_state = torch.load(sae_path, map_location="cpu", weights_only=True, mmap=True)
    decoder_key = _state_key(sae_state, "decoder_linear.weight")
    decoder = sae_state[decoder_key]
    if tuple(decoder.shape) != (MODEL_WIDTH, SAE_WIDTH):
        raise BenchmarkContractError("SAE decoder shape differs from the pin")
    vector = decoder[:, NEUTRAL_SAE_FIXTURE_FEATURE_ID].float()
    vector_norm = float(vector.square().sum().sqrt().item())
    if not math.isfinite(vector_norm) or vector_norm <= 0:
        raise BenchmarkContractError("neutral SAE fixture vector is zero or nonfinite")
    vector = (
        vector * (NEUTRAL_SWITCH_VECTOR_L2 / vector_norm)
    ).to(device="cuda", dtype=torch.bfloat16)
    if not bool(torch.isfinite(vector).all()) or float(vector.float().norm().item()) <= 0:
        raise BenchmarkContractError("BF16 neutral switch vector is invalid")
    del sae_state, decoder

    lens_state = torch.load(lens_path, map_location="cpu", weights_only=True, mmap=True)
    if not {"J", "d_model"} <= set(lens_state):
        raise BenchmarkContractError("J-lens checkpoint keys differ")
    if int(lens_state["d_model"]) != MODEL_WIDTH:
        raise BenchmarkContractError("J-lens width differs")
    available = {int(layer) for layer in lens_state["J"]}
    if not set(J_MAP_LAYERS) <= available:
        raise BenchmarkContractError("J-lens checkpoint lacks a required map")
    matrix_cpu = lens_state["J"][REAL_J_FIXTURE_LAYER]
    if tuple(matrix_cpu.shape) != (MODEL_WIDTH, MODEL_WIDTH):
        raise BenchmarkContractError("real-J fixture shape differs")
    real_j = matrix_cpu.to(device="cuda", dtype=torch.bfloat16).contiguous()
    if not bool(torch.isfinite(real_j).all()):
        raise BenchmarkContractError("real-J BF16 fixture is nonfinite")
    del lens_state, matrix_cpu

    return {
        "torch": torch,
        "model": model,
        "tokenizer": tokenizer,
        "switch_vector": vector,
        "real_j": real_j,
        "model_load_seconds": model_load_seconds,
        "model_load_peak_bytes": model_load_peak,
        "model_snapshot_file_count": sum(
            1 for path in snapshot.rglob("*") if path.is_file()
        ),
    }


def _run_manual_workload(
    artifacts: Mapping[str, Any], *, plan_hash: str, run_id: str
) -> dict[str, Any]:
    torch = artifacts["torch"]
    model = artifacts["model"]
    tokenizer = artifacts["tokenizer"]
    messages, prompt_ids_cpu, padding_repetitions = _rendered_neutral_packet(tokenizer)
    prompt_ids = prompt_ids_cpu.to(device="cuda")
    yes_id, no_id = _single_yes_no_ids(tokenizer)

    def prefill() -> Any:
        with torch.inference_mode():
            return model(
                input_ids=prompt_ids,
                use_cache=True,
                return_dict=True,
            )

    prefill_output, prefill_seconds = _timed_cuda(torch, prefill)
    cache = prefill_output.past_key_values
    current_id = _sample_next(
        prefill_output.logits[0, -1], step=0, stream="neutral-main-benchmark"
    )
    del prefill_output

    trace: dict[str, Any] = {}
    generated: list[int] = []
    decode_seconds = 0.0
    switch_telemetry: dict[str, Any] | None = None
    parent_cache_hash: str | None = None
    event_output_cache_hash: str | None = None
    for step in range(MANUAL_DECODE_STEPS):
        token = torch.tensor([[current_id]], device="cuda", dtype=torch.long)
        if step == 1:
            parent_cache_hash = cache_tensor_sha256(cache)
            handles = _trace_hooks(model, trace)
            switch = Layer50SwitchHook(
                artifacts["switch_vector"], capture_to_cpu=True
            )
            try:
                with switch.register(model.model.layers[SAE_LAYER]):
                    switch.arm(
                        torch.ones(1, dtype=torch.bool),
                        forward_id="neutral-nonzero-layer50-call",
                        event_time=0,
                    )

                    def edited_forward() -> Any:
                        with torch.inference_mode():
                            return model(
                                input_ids=token,
                                past_key_values=cache,
                                use_cache=True,
                                return_dict=True,
                            )

                    output, elapsed = _timed_cuda(torch, edited_forward)
                    event_output_cache_hash = cache_tensor_sha256(
                        output.past_key_values
                    )
            finally:
                _remove_handles(handles)
            switch.validate_complete(expected_calls=1)
            capture = switch.pop_capture(
                expected_forward_id="neutral-nonzero-layer50-call"
            )
            trace["50_pre"] = capture.pre[0, -1].contiguous()
            trace["50_post"] = capture.post[0, -1].contiguous()
            switch_telemetry = switch.telemetry()
        else:

            def decode_forward() -> Any:
                with torch.inference_mode():
                    return model(
                        input_ids=token,
                        past_key_values=cache,
                        use_cache=True,
                        return_dict=True,
                    )

            output, elapsed = _timed_cuda(torch, decode_forward)
        decode_seconds += elapsed
        generated.append(current_id)
        cache = output.past_key_values
        current_id = _sample_next(
            output.logits[0, -1],
            step=step + 1,
            stream="neutral-main-benchmark",
        )
        del output

    expected_trace = {
        *(f"{layer}_post" for layer in range(45, 50)),
        "50_pre",
        "50_post",
        *(f"{layer}_post" for layer in range(51, 79)),
        "final_pre_norm",
    }
    if set(trace) != expected_trace or len(trace) != 36:
        raise BenchmarkContractError(
            f"representative trace differs; missing={sorted(expected_trace-set(trace))}, "
            f"extra={sorted(set(trace)-expected_trace)}"
        )
    for label, residual in trace.items():
        if tuple(residual.shape) != (MODEL_WIDTH,):
            raise BenchmarkContractError(f"trace residual shape differs: {label}")
        if not bool(torch.isfinite(residual.float()).all()):
            raise BenchmarkContractError(f"trace residual is nonfinite: {label}")
    if switch_telemetry is None:
        raise BenchmarkContractError("nonzero switch telemetry is missing")
    if parent_cache_hash is None or event_output_cache_hash is None:
        raise BenchmarkContractError("event cache bindings are missing")
    call = switch_telemetry["call_receipts"][0]
    if call["selected_positions"] != 1 or call["max_abs_delta"] <= 0:
        raise BenchmarkContractError("representative layer-50 edit was not nonzero")

    generated_text = tokenizer.decode(generated, skip_special_tokens=True)
    probe_messages = [
        *messages,
        {"role": "assistant", "content": generated_text},
        {"role": "user", "content": NEUTRAL_YES_NO_QUERY},
    ]
    probe_ids = _token_ids(
        tokenizer.apply_chat_template(
            probe_messages,
            add_generation_prompt=True,
            return_tensors="pt",
        )
    ).to(device="cuda")

    def probe_prefill() -> Any:
        with torch.inference_mode():
            return model(input_ids=probe_ids, use_cache=True, return_dict=True)

    probe_output, probe_prefill_seconds = _timed_cuda(torch, probe_prefill)
    probe_cache = probe_output.past_key_values
    probe_current = _sample_next(
        probe_output.logits[0, -1], step=0, stream="neutral-probe-benchmark"
    )
    del probe_output
    probe_answer_ids: list[int] = []
    probe_decode_seconds = 0.0
    for step in range(PROBE_DECODE_STEPS):
        probe_token = torch.tensor(
            [[probe_current]], device="cuda", dtype=torch.long
        )

        def probe_decode() -> Any:
            with torch.inference_mode():
                return model(
                    input_ids=probe_token,
                    past_key_values=probe_cache,
                    use_cache=True,
                    return_dict=True,
                )

        probe_step_output, elapsed = _timed_cuda(torch, probe_decode)
        probe_decode_seconds += elapsed
        probe_answer_ids.append(probe_current)
        probe_cache = probe_step_output.past_key_values
        probe_current = _sample_next(
            probe_step_output.logits[0, -1],
            step=step + 1,
            stream="neutral-probe-benchmark",
        )
        del probe_step_output

    judge_ids = _token_ids(
        tokenizer.apply_chat_template(
            [
                {"role": "system", "content": NEUTRAL_JUDGE_SYSTEM},
                {"role": "user", "content": NEUTRAL_JUDGE_USER},
            ],
            add_generation_prompt=True,
            return_tensors="pt",
        )
    ).to(device="cuda")

    def judge_prefill() -> Any:
        with torch.inference_mode():
            return model(input_ids=judge_ids, use_cache=True, return_dict=True)

    judge_output, judge_prefill_seconds = _timed_cuda(torch, judge_prefill)
    judge_cache = judge_output.past_key_values
    judge_current = int(torch.argmax(judge_output.logits[0, -1]).item())
    del judge_output
    judge_decode_seconds = 0.0
    judge_answer_ids: list[int] = []
    for _step in range(JUDGE_DECODE_STEPS):
        judge_token = torch.tensor(
            [[judge_current]], device="cuda", dtype=torch.long
        )

        def judge_decode() -> Any:
            with torch.inference_mode():
                return model(
                    input_ids=judge_token,
                    past_key_values=judge_cache,
                    use_cache=True,
                    return_dict=True,
                )

        judge_step_output, elapsed = _timed_cuda(torch, judge_decode)
        judge_decode_seconds += elapsed
        judge_answer_ids.append(judge_current)
        judge_cache = judge_step_output.past_key_values
        judge_current = int(torch.argmax(judge_step_output.logits[0, -1]).item())
        del judge_step_output

    def fixed_forward() -> Any:
        with torch.inference_mode():
            return model.model(
                input_ids=prompt_ids,
                use_cache=False,
                return_dict=True,
            )

    fixed_output, fixed_seconds = _timed_cuda(torch, fixed_forward)
    fixed_shape = tuple(fixed_output.last_hidden_state.shape)
    del fixed_output
    if fixed_shape != (1, int(prompt_ids.shape[1]), MODEL_WIDTH):
        raise BenchmarkContractError("fixed-token representative forward shape differs")

    # Benchmark real-J selected-token readout in a batch large enough to use the
    # B200 tensor cores.  The source is a neutral layer-60 residual.
    source = trace[f"{REAL_J_FIXTURE_LAYER}_post"].to(
        device="cuda", dtype=torch.bfloat16
    )
    source_batch = source.unsqueeze(0).expand(JLENS_BENCHMARK_ROWS, -1).contiguous()
    norm_weight = model.model.norm.weight
    lm_head_weight = model.lm_head.weight
    eps = float(model.model.norm.variance_epsilon)

    def real_j_readout() -> Any:
        with torch.inference_mode():
            return jlens_selected_logits(
                source_batch,
                artifacts["real_j"],
                norm_weight,
                lm_head_weight,
                (yes_id, no_id),
                eps=eps,
                row_batch_size=64,
                transport_dtype=torch.bfloat16,
            )

    warmup, _warmup_seconds = _timed_cuda(torch, real_j_readout)
    if tuple(warmup.shape) != (JLENS_BENCHMARK_ROWS, 2):
        raise BenchmarkContractError("real-J selected readout shape differs")
    del warmup
    readout_hashes: list[str] = []
    jlens_seconds = 0.0
    for _ in range(JLENS_BENCHMARK_REPEATS):
        readout, elapsed = _timed_cuda(torch, real_j_readout)
        jlens_seconds += elapsed
        if not bool(torch.isfinite(readout).all()):
            raise BenchmarkContractError("real-J selected readout is nonfinite")
        readout_hashes.append(tensor_sha256(readout))
        del readout
    if len(set(readout_hashes)) != 1:
        raise BenchmarkContractError("real-J repeated readouts are not byte-identical")

    def identity_readout() -> Any:
        with torch.inference_mode():
            normalized = llama_rms_norm(source_batch, norm_weight, eps=eps)
            return selected_lm_head_logits(
                normalized,
                lm_head_weight,
                (yes_id, no_id),
                row_batch_size=64,
            )

    identity_warmup, _ = _timed_cuda(torch, identity_readout)
    del identity_warmup
    identity_seconds = 0.0
    for _ in range(JLENS_BENCHMARK_REPEATS):
        identity_result, elapsed = _timed_cuda(torch, identity_readout)
        identity_seconds += elapsed
        if tuple(identity_result.shape) != (JLENS_BENCHMARK_ROWS, 2):
            raise BenchmarkContractError("identity selected readout shape differs")
        del identity_result

    # Seven neutral arms exercise all six two-arm contrasts and the exact
    # four-arm sign-oriented target-minus-matched contrast.  These are capacity
    # fixtures only; no target prompt or target outcome enters the tensors.
    delta = artifacts["switch_vector"]
    matched_delta = torch.roll(delta, shifts=1)
    isotropic_delta = torch.flip(delta, dims=(0,))
    arm_names = (
        "never",
        "target_supp",
        "target_amp",
        "matched_supp",
        "matched_amp",
        "isotropic_supp",
        "isotropic_amp",
    )
    arm_sources = torch.stack(
        (
            source,
            source - delta,
            source + delta,
            source - matched_delta,
            source + matched_delta,
            source - isotropic_delta,
            source + isotropic_delta,
        )
    ).to(dtype=torch.bfloat16)
    with torch.inference_mode():
        _, arm_normalized = jlens_normalized_hidden(
            arm_sources,
            artifacts["real_j"],
            norm_weight,
            eps=eps,
            row_batch_size=7,
            transport_dtype=torch.bfloat16,
        )

    def full_vocab() -> Any:
        with torch.inference_mode():
            return _chunked_full_vocab_logits(arm_normalized, lm_head_weight)

    full_logits, full_vocab_seconds = _timed_cuda(torch, full_vocab)
    if tuple(full_logits.shape) != (len(arm_names), TOKENIZER_SIZE):
        raise BenchmarkContractError("full-vocabulary fixture shape differs")

    packed_tensors: dict[str, Any] = {}
    packing_rates: dict[str, float] = {}
    pair_arm_indexes = {
        VOCABULARY_CONTRASTS[index]: index + 1 for index in range(6)
    }
    packed_rows: list[dict[str, Any]] = []
    checkpoints_by_k = {
        k: [
            checkpoint
            for checkpoint in VOCABULARY_CHECKPOINTS
            if VOCABULARY_TOP_K_BY_CHECKPOINT[checkpoint] == k
        ]
        for k in (512, 2000)
    }
    if sorted(
        checkpoint for checkpoints in checkpoints_by_k.values() for checkpoint in checkpoints
    ) != sorted(VOCABULARY_CHECKPOINTS):
        raise BenchmarkContractError("neutral vocabulary checkpoints differ")
    for k, checkpoints in checkpoints_by_k.items():
        # Include device-to-host materialization in every packing rate.  Archive
        # timing starts only after these CPU arrays exist, so excluding this
        # transfer would underprice the target workload.
        _sync(torch)
        raw_started = time.perf_counter()
        for checkpoint in checkpoints:
            raw = _stable_raw_topk(full_logits, k=k)
            tensor_prefix = f"raw_{checkpoint}_k{k}"
            for field, tensor in raw.items():
                packed_tensors[f"{tensor_prefix}_{field}"] = (
                    tensor.detach().cpu().contiguous()
                )
            for arm_index, arm_name in enumerate(arm_names):
                packed_rows.append(
                    {
                        "packed_row_id": f"raw-{checkpoint}-k{k}-{arm_name}",
                        "row_kind": "raw_topk",
                        "checkpoint": checkpoint,
                        "k": k,
                        "contrast_id": None,
                        "arm_name": arm_name,
                        "tensor_prefix": tensor_prefix,
                        "tensor_row_offset": arm_index,
                    }
                )
        _sync(torch)
        raw_seconds = time.perf_counter() - raw_started
        if raw_seconds <= 0:
            raise BenchmarkContractError("raw top-k timer did not advance")
        packing_rates[f"raw_topk_k{k}_rows_per_second"] = (
            len(checkpoints) * len(arm_names) / raw_seconds
        )

        _sync(torch)
        pair_started = time.perf_counter()
        for checkpoint in checkpoints:
            for contrast_id, arm_index in pair_arm_indexes.items():
                pair = pack_pair_delta_union(
                    full_logits[arm_index], full_logits[0], k=k
                )
                safe_id = contrast_id.replace("_minus_never", "")
                tensor_prefix = f"pair_{checkpoint}_k{k}_{safe_id}"
                for field, tensor in pair.items():
                    packed_tensors[f"{tensor_prefix}_{field}"] = (
                        tensor.detach().cpu().contiguous()
                    )
                packed_rows.append(
                    {
                        "packed_row_id": f"pair-{checkpoint}-k{k}-{contrast_id}",
                        "row_kind": "pair_delta_union",
                        "checkpoint": checkpoint,
                        "k": k,
                        "contrast_id": contrast_id,
                        "arm_name": None,
                        "tensor_prefix": tensor_prefix,
                        "tensor_row_offset": 0,
                    }
                )
        _sync(torch)
        pair_seconds = time.perf_counter() - pair_started
        if pair_seconds <= 0:
            raise BenchmarkContractError("pair-union timer did not advance")
        packing_rates[f"pair_union_k{k}_rows_per_second"] = (
            len(checkpoints) * 6 / pair_seconds
        )

        _sync(torch)
        sign_started = time.perf_counter()
        for checkpoint in checkpoints:
            sign = pack_four_arm_sign_union(
                full_logits[1],
                full_logits[2],
                full_logits[3],
                full_logits[4],
                k=k,
            )
            tensor_prefix = f"sign_{checkpoint}_k{k}"
            for field, tensor in sign.items():
                packed_tensors[f"{tensor_prefix}_{field}"] = (
                    tensor.detach().cpu().contiguous()
                )
            packed_rows.append(
                {
                    "packed_row_id": (
                        f"sign-{checkpoint}-k{k}-{VOCABULARY_CONTRASTS[-1]}"
                    ),
                    "row_kind": "four_arm_sign_union",
                    "checkpoint": checkpoint,
                    "k": k,
                    "contrast_id": VOCABULARY_CONTRASTS[-1],
                    "arm_name": None,
                    "tensor_prefix": tensor_prefix,
                    "tensor_row_offset": 0,
                }
            )
        _sync(torch)
        sign_seconds = time.perf_counter() - sign_started
        if sign_seconds <= 0:
            raise BenchmarkContractError("sign-union timer did not advance")
        packing_rates[f"sign_union_k{k}_rows_per_second"] = (
            len(checkpoints) / sign_seconds
        )
    expected_packed_rows = _expected_packed_fixture_rows()
    # Packing is timed by representation (raw, pair, sign), whereas the
    # archive contract is ordered by checkpoint.  Canonicalize by the frozen
    # row ID before comparing/writing; ordering the timed loops themselves
    # would mix the three independently measured packing rates.
    packed_by_id = {
        str(row["packed_row_id"]): row
        for row in packed_rows
    }
    if len(packed_by_id) != len(packed_rows) or set(packed_by_id) != {
        str(row["packed_row_id"]) for row in expected_packed_rows
    }:
        raise BenchmarkContractError("neutral packed checkpoint ID set differs")
    packed_rows = [
        packed_by_id[str(expected["packed_row_id"])]
        for expected in expected_packed_rows
    ]
    if packed_rows != expected_packed_rows:
        raise BenchmarkContractError("neutral packed checkpoint rows differ")
    packed_numeric_payload_bytes = _packed_numeric_bytes(packed_tensors)

    del cache, probe_cache, judge_cache, source_batch, full_logits, arm_normalized
    torch.cuda.empty_cache()
    total_peak = int(torch.cuda.max_memory_allocated())
    total_reserved_peak = int(torch.cuda.max_memory_reserved())

    ordered_labels = [
        *(f"{layer}_post" for layer in range(45, 50)),
        "50_pre",
        "50_post",
        *(f"{layer}_post" for layer in range(51, 79)),
        "final_pre_norm",
    ]
    residuals = torch.stack(
        [trace[label].to(dtype=torch.bfloat16) for label in ordered_labels]
    ).contiguous()
    if tuple(residuals.shape) != (36, MODEL_WIDTH):
        raise BenchmarkContractError("archive fixture trace shape differs")

    return {
        "residuals": residuals,
        "residual_rows": build_representative_source_index_rows(
            ordered_labels,
            plan_hash=plan_hash,
            run_id=run_id,
            prefix_token_ids_sha256=tensor_sha256(prompt_ids_cpu),
            predicted_token_id=generated[2],
            intervention_sha256=tensor_sha256(artifacts["switch_vector"]),
            parent_cache_sha256=parent_cache_hash,
            output_cache_sha256=event_output_cache_hash,
        ),
        "packed_tensors": packed_tensors,
        "packed_rows": packed_rows,
        "packed_numeric_payload_bytes": packed_numeric_payload_bytes,
        "metrics": {
            "model_load_seconds": float(artifacts["model_load_seconds"]),
            "prefill_tokens_per_second": int(prompt_ids.shape[1]) / prefill_seconds,
            "decode_tokens_per_second": MANUAL_DECODE_STEPS / decode_seconds,
            "probe_items_per_second_observed": 1.0
            / (probe_prefill_seconds + probe_decode_seconds),
            "probe_answer_tokens_per_second_observed": PROBE_DECODE_STEPS
            / probe_decode_seconds,
            "fixed_forwards_per_second": 1.0 / fixed_seconds,
            "local_judge_items_per_second_observed": 1.0
            / (judge_prefill_seconds + judge_decode_seconds),
            "local_judge_answer_tokens_per_second_observed": JUDGE_DECODE_STEPS
            / judge_decode_seconds,
            "real_j_states_per_second": (
                JLENS_BENCHMARK_ROWS * JLENS_BENCHMARK_REPEATS / jlens_seconds
            ),
            "identity_states_per_second": (
                JLENS_BENCHMARK_ROWS * JLENS_BENCHMARK_REPEATS / identity_seconds
            ),
            "full_vocab_rows_per_second": len(arm_names) / full_vocab_seconds,
            **packing_rates,
        },
        "fixture": {
            "neutral_packet_spec_sha256": NEUTRAL_PACKET_SPEC_SHA256,
            "neutral_padding_repetitions": padding_repetitions,
            "prefill_tokens": int(prompt_ids.shape[1]),
            "prefill_token_ids_sha256": tensor_sha256(prompt_ids_cpu),
            "manual_decode_steps": MANUAL_DECODE_STEPS,
            "manual_decode_token_ids_sha256": hashlib.sha256(
                canonical_json_bytes(generated)
            ).hexdigest(),
            "probe_tokens": int(probe_ids.shape[1]),
            "probe_answer_steps": PROBE_DECODE_STEPS,
            "probe_answer_token_ids_sha256": hashlib.sha256(
                canonical_json_bytes(probe_answer_ids)
            ).hexdigest(),
            "judge_tokens": int(judge_ids.shape[1]),
            "judge_answer_steps": JUDGE_DECODE_STEPS,
            "judge_answer_token_ids_sha256": hashlib.sha256(
                canonical_json_bytes(judge_answer_ids)
            ).hexdigest(),
            "yes_token_id": yes_id,
            "no_token_id": no_id,
            "switch_fixture_feature_id": NEUTRAL_SAE_FIXTURE_FEATURE_ID,
            "switch_vector_sha256": tensor_sha256(artifacts["switch_vector"]),
            "switch_telemetry": switch_telemetry,
            "trace_states": ordered_labels,
            "real_j_layer": REAL_J_FIXTURE_LAYER,
            "real_j_runtime_dtype": str(artifacts["real_j"].dtype),
            "real_j_selected_readout_sha256": readout_hashes[0],
        },
        "memory": {
            "model_load_peak_allocated_bytes": artifacts["model_load_peak_bytes"],
            "benchmark_peak_allocated_bytes": total_peak,
            "benchmark_peak_reserved_bytes": total_reserved_peak,
        },
    }


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _write_packed_vocab_fixture(
    block: Any,
    *,
    tensors: Mapping[str, Any],
    packed_rows: Sequence[Mapping[str, Any]],
    tokenizer: Any,
) -> dict[str, Any]:
    """Write/read actual packed arrays, row index, and global token metadata."""

    import pyarrow as pa
    import pyarrow.parquet as pq
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    directory = block.partial_path / "vocabulary"
    directory.mkdir(parents=True, exist_ok=False)
    array_path = directory / "packed-neutral-fixture.safetensors"
    row_index_path = directory / "packed-neutral-row-index.parquet"
    token_path = directory / "global-token-metadata.parquet"
    normalized_rows = [dict(row) for row in packed_rows]
    if normalized_rows != _expected_packed_fixture_rows():
        raise BenchmarkContractError("packed fixture row inventory differs")
    inventory_sha256 = hashlib.sha256(
        canonical_json_bytes(normalized_rows)
    ).hexdigest()
    if inventory_sha256 != PACKED_FIXTURE_INVENTORY_SHA256:
        raise BenchmarkContractError("packed fixture inventory hash differs")
    write_started = time.perf_counter()
    cpu_tensors = {
        str(key): value.detach().cpu().contiguous() for key, value in tensors.items()
    }
    save_file(cpu_tensors, str(array_path))
    _fsync_file(array_path)
    row_table = pa.Table.from_pylist(normalized_rows)
    pq.write_table(row_table, row_index_path, compression="zstd", use_dictionary=True)
    _fsync_file(row_index_path)

    special_ids = {int(value) for value in tokenizer.all_special_ids}
    added_ids = {int(value) for value in tokenizer.added_tokens_decoder}
    token_ids: list[int] = []
    raw_pieces: list[bytes] = []
    decoded_pieces: list[str] = []
    is_special: list[bool] = []
    is_added: list[bool] = []
    is_empty: list[bool] = []
    for token_id in range(TOKENIZER_SIZE):
        raw = tokenizer.convert_ids_to_tokens(token_id)
        raw_text = "" if raw is None else str(raw)
        decoded = tokenizer.decode(
            [token_id],
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        )
        token_ids.append(token_id)
        raw_pieces.append(raw_text.encode("utf-8"))
        decoded_pieces.append(str(decoded))
        is_special.append(token_id in special_ids)
        is_added.append(token_id in added_ids)
        is_empty.append(not raw_text or not str(decoded))
    token_table = pa.table(
        {
            "token_id": pa.array(token_ids, type=pa.int32()),
            "raw_token_bytes": pa.array(raw_pieces, type=pa.binary()),
            "decoded_piece": pa.array(decoded_pieces, type=pa.string()),
            "is_special": pa.array(is_special, type=pa.bool_()),
            "is_added": pa.array(is_added, type=pa.bool_()),
            "is_empty_looking": pa.array(is_empty, type=pa.bool_()),
        }
    )
    pq.write_table(token_table, token_path, compression="zstd", use_dictionary=True)
    _fsync_file(token_path)
    write_seconds = time.perf_counter() - write_started

    read_started = time.perf_counter()
    with safe_open(str(array_path), framework="pt", device="cpu") as handle:
        if set(handle.keys()) != set(cpu_tensors):
            raise BenchmarkContractError("packed safetensors key inventory differs")
        for key, expected in cpu_tensors.items():
            observed = handle.get_tensor(key)
            if observed.dtype != expected.dtype or observed.shape != expected.shape:
                raise BenchmarkContractError(f"packed tensor contract differs: {key}")
            if not bool(torch.equal(observed, expected)):
                raise BenchmarkContractError(f"packed tensor readback differs: {key}")
    reopened_rows = pq.read_table(row_index_path)
    reopened_tokens = pq.read_table(token_path)
    if (
        reopened_rows.num_rows != len(normalized_rows)
        or reopened_rows.to_pylist() != normalized_rows
    ):
        raise BenchmarkContractError("packed row-index count differs")
    if reopened_tokens.num_rows != TOKENIZER_SIZE:
        raise BenchmarkContractError("global token-metadata row count differs")
    if reopened_tokens.column("token_id").to_pylist() != list(range(TOKENIZER_SIZE)):
        raise BenchmarkContractError("global token-metadata IDs differ")
    read_seconds = time.perf_counter() - read_started
    total_bytes = sum(
        path.stat().st_size for path in (array_path, row_index_path, token_path)
    )
    return {
        "packed_arrays_bytes": array_path.stat().st_size,
        "packed_numeric_payload_bytes": _packed_numeric_bytes(cpu_tensors),
        "packed_row_index_bytes": row_index_path.stat().st_size,
        "packed_row_count": len(packed_rows),
        "packed_row_inventory_sha256": inventory_sha256,
        "token_metadata_bytes": token_path.stat().st_size,
        "token_metadata_rows": TOKENIZER_SIZE,
        "total_bytes": total_bytes,
        "write_seconds": write_seconds,
        "read_seconds": read_seconds,
        "packed_arrays_sha256": sha256_file(array_path),
        "packed_row_index_sha256": sha256_file(row_index_path),
        "token_metadata_sha256": sha256_file(token_path),
    }


def run_benchmark(
    *,
    cache_dir: Path,
    artifact_root: str | Path | None,
    expected_volume_id: str,
    run_id: str,
    plan_hash: str,
    prefix_count: int,
    gpu_hourly_usd: Decimal | str | float,
) -> Path:
    """Run the target-blind benchmark and return its sealed external path."""

    import torch

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise BenchmarkContractError("benchmark requires exactly one CUDA GPU")
    properties = torch.cuda.get_device_properties(0)
    if "B200" not in properties.name.upper():
        raise BenchmarkContractError(f"benchmark requires B200, got {properties.name!r}")
    if int(properties.total_memory) < 170 * 1024**3:
        raise BenchmarkContractError("B200 exposes less than the 170 GiB floor")
    if not isinstance(plan_hash, str) or not HEX64.fullmatch(plan_hash):
        raise BenchmarkContractError("plan_hash must be 64 lowercase hex digits")
    workload = build_exact_workload(prefix_count)

    root = paths.require_external_artifact_root(
        artifact_root,
        expected_volume_id=expected_volume_id,
        write_read_probe=True,
    )
    cache_dir = cache_dir.expanduser().resolve(strict=True)
    try:
        cache_relative = cache_dir.relative_to(root)
    except ValueError as exc:
        raise BenchmarkContractError(
            "local-only artifact cache must be beneath the guarded volume"
        ) from exc
    if cache_dir.is_symlink():
        raise BenchmarkContractError("artifact cache root may not be a symlink")

    transaction = RunTransaction.start(
        phase=BENCHMARK_PHASE,
        run_id=run_id,
        artifact_root=root,
        expected_volume_id=expected_volume_id,
        metadata={
            "outcome_blind": True,
            "prior_outcome_inputs": [],
            "plan_hash": plan_hash,
            "prefix_count": prefix_count,
            "neutral_packet_spec_sha256": NEUTRAL_PACKET_SPEC_SHA256,
        },
    )
    artifacts = _load_artifacts(cache_dir)
    workload_result = _run_manual_workload(
        artifacts, plan_hash=plan_hash, run_id=run_id
    )

    block = transaction.begin_block("neutral-bf16-archive")
    write_started = time.perf_counter()
    shard_receipt = block.write_source_shard(
        "neutral-trace",
        workload_result["residuals"],
        workload_result["residual_rows"],
    )
    vocab_sample = _write_packed_vocab_fixture(
        block,
        tensors=workload_result["packed_tensors"],
        packed_rows=workload_result["packed_rows"],
        tokenizer=artifacts["tokenizer"],
    )
    block_path = block.complete(
        metadata={
            "outcome_blind": True,
            "prior_outcome_inputs": [],
            "plan_hash": plan_hash,
            "source_index_schema_sha256": SOURCE_INDEX_SCHEMA_SHA256,
        }
    )
    write_seconds = time.perf_counter() - write_started
    archived_bytes = (
        shard_receipt.residual_bytes
        + shard_receipt.index_bytes
        + int(vocab_sample["total_bytes"])
    )
    if write_seconds <= 0 or archived_bytes <= 0:
        raise BenchmarkContractError("archive write timing or byte count is invalid")

    read_started = time.perf_counter()
    reopened = open_source_shard(block_path, shard_receipt)
    read_seconds = time.perf_counter() - read_started
    if read_seconds <= 0 or not torch.equal(
        reopened.view(torch.int16),
        workload_result["residuals"].view(torch.int16),
    ):
        raise BenchmarkContractError("BF16 archive readback differs")

    read_seconds += float(vocab_sample["read_seconds"])
    metrics = dict(workload_result["metrics"])
    metrics["archive_write_bytes_per_second"] = archived_bytes / write_seconds
    metrics["archive_read_bytes_per_second"] = archived_bytes / read_seconds
    extrapolation = extrapolate_capacity(
        metrics,
        {
            "rows": shard_receipt.rows,
            "residual_bytes": shard_receipt.residual_bytes,
            "index_bytes": shard_receipt.index_bytes,
            "packed_arrays_bytes": int(vocab_sample["packed_arrays_bytes"]),
            "packed_numeric_payload_bytes": int(
                vocab_sample["packed_numeric_payload_bytes"]
            ),
            "packed_row_index_bytes": int(vocab_sample["packed_row_index_bytes"]),
            "packed_row_count": int(vocab_sample["packed_row_count"]),
            "token_metadata_bytes": int(vocab_sample["token_metadata_bytes"]),
        },
        gpu_hourly_usd=gpu_hourly_usd,
        workload=workload,
    )

    receipt: dict[str, Any] = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "status": "pass",
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "plan_hash": plan_hash,
        "benchmark_id": run_id,
        "created_at_utc": _utc_now(),
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
            "expected_volume_id": expected_volume_id,
            "cache_relative_directory": cache_relative.as_posix(),
        },
        "artifacts": {
            "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "dtype": "bfloat16"},
            "sae": {
                "id": SAE_ID,
                "revision": SAE_REVISION,
                "file_sha256": SAE_FILE_SHA256,
                "runtime_fixture_dtype": "bfloat16",
            },
            "jacobian_lens": {
                "id": JLENS_ID,
                "revision": JLENS_REVISION,
                "file_sha256": JLENS_FILE_SHA256,
                "runtime_fixture_layer": REAL_J_FIXTURE_LAYER,
                "runtime_fixture_dtype": "bfloat16",
            },
            "model_snapshot_file_count": artifacts["model_snapshot_file_count"],
        },
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu_name": properties.name,
            "gpu_total_memory_bytes": int(properties.total_memory),
            "source_sha256": sha256_file(Path(__file__)),
        },
        "neutral_fixture": workload_result["fixture"],
        "technical_gates": {
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
        },
        "measurements": metrics,
        "peak_gpu_memory": workload_result["memory"],
        "archive_sample": {
            "rows": shard_receipt.rows,
            "width": shard_receipt.width,
            "dtype": shard_receipt.dtype,
            "residual_bytes": shard_receipt.residual_bytes,
            "index_bytes": shard_receipt.index_bytes,
            "write_seconds": write_seconds,
            "read_seconds": read_seconds,
            "residual_sha256": shard_receipt.residual_sha256,
            "index_sha256": shard_receipt.index_sha256,
            "packed_vocabulary": vocab_sample,
        },
        "source_index_contract": {
            "fields": list(SOURCE_INDEX_FIELDS),
            "schema_sha256": SOURCE_INDEX_SCHEMA_SHA256,
            "representative_rows": len(workload_result["residual_rows"]),
        },
        "exact_max_workload": workload.as_dict(),
        "workload_contract_sha256": workload_contract_sha256(workload),
        "capacity_authorization_proposal": extrapolation,
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(receipt)
    ).hexdigest()
    transaction.write_json("benchmark_receipt.json", receipt)
    final_path = transaction.complete(
        metadata={
            "outcome_blind": True,
            "prior_outcome_inputs": [],
            "benchmark_receipt_sha256": receipt["receipt_sha256"],
        }
    )
    return final_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--plan-hash", required=True)
    parser.add_argument("--prefix-count", type=int, required=True)
    parser.add_argument("--gpu-hourly-usd", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    final_path = run_benchmark(
        cache_dir=args.cache_dir,
        artifact_root=args.artifact_root,
        expected_volume_id=args.volume_id,
        run_id=args.run_id,
        plan_hash=args.plan_hash,
        prefix_count=args.prefix_count,
        gpu_hourly_usd=args.gpu_hourly_usd,
    )
    print(
        json.dumps(
            {"status": "pass", "sealed_benchmark_directory": str(final_path)},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
