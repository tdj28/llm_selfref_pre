#!/usr/bin/env python3
"""Run one non-scientific, execution-bound B200 smoke before Stage A.

The smoke exercises the exact production loader, arc capture, single-use BF16
hook, one real-J transport, selected-logit readout, and a tiny deterministic
top-k replay.  Its prompt and generic direction are disjoint from Stage A and
Stage B.  The resulting receipt is operational evidence only: it is outside
the raw namespace, contains no target feature or target outcome, and is never
an admissible scientific-gate or dose-selection input.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_realization_validation import (  # noqa: E402
    controls,
    preexecution,
    protocol,
    runner,
    runtime,
    runpod_preflight,
)


SMOKE_SCHEMA_VERSION = 1
SMOKE_RECEIPT_TYPE = "b200_execution_smoke_v1"
SMOKE_SOURCE_RELATIVE_PATH = (
    "experiments/consciousness_sae_realization_validation/smoke_test.py"
)
SMOKE_PROMPT_ID = "neutral_smoke01"
SMOKE_PROMPT = {
    "system": protocol.NEUTRAL_SYSTEM,
    "user": "What item is commonly hung on a wall to show the time?",
}
SMOKE_EDIT_LAYER = 50
SMOKE_DOSE_FRACTION = 0.0025
SMOKE_SELECTED_TOKEN_COUNT = 64
SMOKE_TOP_K = 8
SMOKE_EXPECTED_MODEL_FORWARD_COUNT = 4  # prefix, clean token, plus, minus
SMOKE_RECEIPT_SUBDIRECTORY = "operational_smoke_receipts"

HEX64 = re.compile(r"[0-9a-f]{64}")

SMOKE_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "receipt_type",
        "status",
        "study_id",
        "protocol_version",
        "run_id",
        "plan_manifest_sha256",
        "plan_source_inventory_sha256",
        "smoke_source_sha256",
        "preexecution_authorization_sha256",
        "ownership_receipt_sha256",
        "guest_receipt_sha256",
        "cache_receipt_sha256",
        "campaign_identity_sha256",
        "campaign_started_at_unix",
        "provider_terminate_at_unix",
        "completed_at_unix",
        "external_receipt_relative_path",
        "execution_binding",
        "prompt_receipt",
        "edit_contract",
        "capture_receipt",
        "realization_receipt",
        "transport_receipt",
        "replay_receipt",
        "runtime_metadata",
        "resource",
        "model_forward_count",
        "expected_model_forward_count",
        "mundane_smoke_prompt_render_count",
        "stage_a_prompt_render_count",
        "stage_b_prompt_render_count",
        "paper_prompt_render_count",
        "target_prompt_render_count",
        "target_feature_vector_count",
        "target_outcome_count",
        "behavioral_outcome_count",
        "scientific_gate_input_count",
        "dose_selection_input_count",
        "scientific_gate_eligible",
        "dose_selection_eligible",
        "result_reuse_prohibited",
        "prior_outcome_inputs",
        "receipt_sha256",
    }
)


class SmokeTestError(RuntimeError):
    """A fail-closed operational smoke error."""


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _validate_constants() -> None:
    if SMOKE_PROMPT_ID in set(protocol.STAGE_A_PROMPT_IDS) | set(
        protocol.STAGE_B_PROMPT_IDS
    ):
        raise SmokeTestError("smoke prompt ID overlaps a scientific prompt")
    scientific_payloads = {
        (protocol.prompt_payload(prompt_id)["system"], protocol.prompt_payload(prompt_id)["user"])
        for prompt_id in (*protocol.STAGE_A_PROMPT_IDS, *protocol.STAGE_B_PROMPT_IDS)
    }
    if (SMOKE_PROMPT["system"], SMOKE_PROMPT["user"]) in scientific_payloads:
        raise SmokeTestError("smoke prompt payload overlaps a scientific prompt")
    if SMOKE_EDIT_LAYER != protocol.SAE_LAYER:
        raise SmokeTestError("smoke edit is not at the production layer-50 hook")
    if SMOKE_DOSE_FRACTION <= 0 or SMOKE_DOSE_FRACTION > min(protocol.DOSE_GRID):
        raise SmokeTestError("smoke dose is not a tiny, bounded diagnostic dose")
    if SMOKE_TOP_K <= 0 or SMOKE_TOP_K > SMOKE_SELECTED_TOKEN_COUNT:
        raise SmokeTestError("smoke top-k contract is invalid")


def render_smoke_prompt(tokenizer: Any) -> tuple[tuple[int, ...], dict[str, Any]]:
    """Render and receipt the one disjoint mundane smoke prompt."""

    _validate_constants()
    messages = (
        {"role": "system", "content": SMOKE_PROMPT["system"]},
        {"role": "user", "content": SMOKE_PROMPT["user"]},
    )
    token_ids = tokenizer.apply_chat_template(
        list(messages), tokenize=True, add_generation_prompt=True
    )
    if hasattr(token_ids, "tolist"):
        token_ids = token_ids.tolist()
    if token_ids and isinstance(token_ids[0], list):
        if len(token_ids) != 1:
            raise SmokeTestError("smoke chat template produced a batch")
        token_ids = token_ids[0]
    result = tuple(int(value) for value in token_ids)
    if (
        len(result) < 2
        or min(result) < 0
        or max(result) >= protocol.VOCAB_SIZE
    ):
        raise SmokeTestError("smoke chat template produced invalid token IDs")
    receipt = {
        "prompt_id": SMOKE_PROMPT_ID,
        "prompt_role": "disjoint_mundane_operational_smoke_only",
        "prompt_payload_sha256": protocol.canonical_sha256(SMOKE_PROMPT),
        "token_ids": list(result),
        "token_ids_sha256": runtime.token_ids_sha256(result),
        "token_count": len(result),
        "overlaps_stage_a_or_b": False,
        "target_prompt": False,
    }
    return result, receipt


def smoke_direction() -> Any:
    """Return the smoke-only generic direction; never a scientific vector."""

    import numpy as np

    torch = runtime._torch()
    seed = protocol.seed64("b200-execution-smoke-generic-direction", SMOKE_EDIT_LAYER)
    rng = np.random.Generator(np.random.PCG64(seed))
    values = rng.standard_normal(protocol.WIDTH).astype(np.float32)
    values /= max(float(np.sqrt(np.mean(values * values))), 1e-30)
    result = torch.from_numpy(values).contiguous()
    if tuple(result.shape) != (protocol.WIDTH,) or not bool(torch.isfinite(result).all()):
        raise SmokeTestError("smoke generic direction is malformed")
    return result


def smoke_selected_token_panel() -> tuple[int, ...]:
    """A small deterministic logit panel separate from scientific panels."""

    offset = protocol.seed64("b200-execution-smoke-logit-panel") % protocol.VOCAB_SIZE
    # 7,919 is coprime to 128,256; these IDs are unique.
    result = tuple(
        int((offset + 7_919 * index) % protocol.VOCAB_SIZE)
        for index in range(SMOKE_SELECTED_TOKEN_COUNT)
    )
    if len(result) != len(set(result)):
        raise SmokeTestError("smoke selected-token panel is not unique")
    return result


def _stable_panel_topk(
    scores: Any,
    token_ids: Sequence[int],
    *,
    largest: bool,
) -> list[dict[str, Any]]:
    values = scores.detach().to(device="cpu", dtype=runtime._torch().float32).reshape(-1)
    ids = tuple(int(value) for value in token_ids)
    if int(values.numel()) != len(ids) or not bool(runtime._torch().isfinite(values).all()):
        raise SmokeTestError("smoke selected-logit scores are malformed")
    pairs = [(token_id, float(values[index].item())) for index, token_id in enumerate(ids)]
    pairs.sort(key=(lambda item: (-item[1], item[0])) if largest else (lambda item: (item[1], item[0])))
    return [
        {"rank": rank, "token_id": token_id, "score": score}
        for rank, (token_id, score) in enumerate(pairs[:SMOKE_TOP_K], start=1)
    ]


def _validate_topk_rows(rows: Any, *, panel: set[int], largest: bool) -> None:
    if not isinstance(rows, list) or len(rows) != SMOKE_TOP_K:
        raise SmokeTestError("smoke top-k row count differs")
    observed: list[tuple[int, float]] = []
    for rank, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping) or set(row) != {"rank", "token_id", "score"}:
            raise SmokeTestError("smoke top-k schema differs")
        if row["rank"] != rank or row["token_id"] not in panel or not _finite_number(row["score"]):
            raise SmokeTestError("smoke top-k row is invalid")
        observed.append((int(row["token_id"]), float(row["score"])))
    if len({token_id for token_id, _ in observed}) != len(observed):
        raise SmokeTestError("smoke top-k token IDs repeat")
    expected = sorted(
        observed,
        key=(lambda item: (-item[1], item[0])) if largest else (lambda item: (item[1], item[0])),
    )
    if observed != expected:
        raise SmokeTestError("smoke top-k rows are not stably ordered")


def _require_exact_fields(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SmokeTestError(f"{label} schema differs")
    return value


def _capture_summary(trace: runtime.ArcTrace, *, branch: str) -> dict[str, Any]:
    torch = runtime._torch()
    if tuple(trace.residual_by_layer) != protocol.J_LAYERS:
        raise SmokeTestError(f"{branch} did not capture exactly layers 45--78")
    values = [trace.residual_by_layer[layer] for layer in protocol.J_LAYERS]
    values.append(trace.final_residual)
    if any(
        tuple(value.shape) != (protocol.WIDTH,) or value.dtype != torch.bfloat16
        for value in values
    ):
        raise SmokeTestError(f"{branch} capture shape/dtype differs")
    stack = torch.stack(values).contiguous()
    return {
        "branch": branch,
        "captured_j_layers": list(protocol.J_LAYERS),
        "captured_j_layer_count": len(protocol.J_LAYERS),
        "final_state_captured": True,
        "arc_tensor_sha256": runtime.tensor_sha256(stack),
    }


def _source_binding(plan_dir: Path) -> tuple[str, str]:
    source_path = plan_dir.expanduser().resolve(strict=True) / "source_files.json"
    source_inventory_sha256 = protocol.sha256_file(source_path)
    try:
        source_inventory = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SmokeTestError("plan source inventory is unreadable") from exc
    rows = source_inventory.get("files") if isinstance(source_inventory, Mapping) else None
    if not isinstance(rows, list):
        raise SmokeTestError("plan source inventory is malformed")
    matches = [row for row in rows if row.get("path") == SMOKE_SOURCE_RELATIVE_PATH]
    source = REPO_ROOT / SMOKE_SOURCE_RELATIVE_PATH
    if len(matches) != 1 or matches[0].get("sha256") != protocol.sha256_file(source):
        raise SmokeTestError("smoke runner is not bound by the frozen source inventory")
    return source_inventory_sha256, str(matches[0]["sha256"])


def smoke_receipt_path(volume_root: Path, *, volume_id: str, run_id: str) -> Path:
    if not isinstance(run_id, str) or controls.SAFE_RUN_ID.fullmatch(run_id) is None:
        raise SmokeTestError("unsafe smoke run ID")
    try:
        root = controls.require_volume_root(volume_root, volume_id=volume_id)
    except controls.ControlViolation as exc:
        raise SmokeTestError(f"smoke volume failed validation: {exc}") from exc
    destination = (
        root
        / protocol.STUDY_SLUG
        / protocol.STUDY_ID
        / SMOKE_RECEIPT_SUBDIRECTORY
        / f"{run_id}.json"
    )
    raw_root = root.joinpath(*controls.RAW_NAMESPACE)
    if destination == raw_root or raw_root in destination.parents:
        raise SmokeTestError("smoke receipt must remain outside the raw namespace")
    current = root
    for part in destination.relative_to(root).parent.parts:
        current = current / part
        if current.is_symlink():
            raise SmokeTestError("smoke receipt parent contains a symlink")
        if current.exists() and not current.is_dir():
            raise SmokeTestError("smoke receipt parent contains a non-directory")
    if destination.exists() or destination.is_symlink():
        raise SmokeTestError("smoke receipt path is not fresh")
    return destination


def validate_external_receipt_file(
    *,
    volume_root: Path,
    receipt_path: Path,
    receipt: Mapping[str, Any],
) -> str:
    """Require the receipt's exact canonical external single-link file."""

    root = volume_root.expanduser().resolve(strict=True)
    relative_text = receipt.get("external_receipt_relative_path")
    if not isinstance(relative_text, str):
        raise SmokeTestError("smoke external receipt path is missing")
    relative = PurePosixPath(relative_text)
    if (
        relative.is_absolute()
        or relative.as_posix() != relative_text
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise SmokeTestError("smoke external receipt path is unsafe")
    expected = root.joinpath(*relative.parts)
    supplied = Path(os.path.abspath(receipt_path.expanduser()))
    if supplied != expected:
        raise SmokeTestError("smoke receipt is not at its exact external path")
    if supplied.is_symlink() or not supplied.is_file() or supplied.stat().st_nlink != 1:
        raise SmokeTestError("smoke receipt is not a single-link regular file")
    try:
        supplied.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise SmokeTestError("smoke receipt escapes the volume root") from exc
    expected_bytes = protocol.canonical_json_bytes(dict(receipt)) + b"\n"
    if supplied.read_bytes() != expected_bytes:
        raise SmokeTestError("smoke receipt is not canonical JSON")
    return protocol.sha256_file(supplied)


def _seal(core: Mapping[str, Any]) -> dict[str, Any]:
    return {**dict(core), "receipt_sha256": protocol.canonical_sha256(dict(core))}


def validate_smoke_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_plan_hash: str | None = None,
    expected_run_id: str | None = None,
    expected_authorization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a smoke receipt without making it a scientific gate."""

    if not isinstance(receipt, Mapping) or set(receipt) != SMOKE_RECEIPT_FIELDS:
        raise SmokeTestError("smoke receipt schema differs")
    supplied = receipt.get("receipt_sha256")
    core = dict(receipt)
    core.pop("receipt_sha256", None)
    if not _is_hex64(supplied) or supplied != protocol.canonical_sha256(core):
        raise SmokeTestError("smoke receipt self-hash differs")
    if (
        receipt["schema_version"] != SMOKE_SCHEMA_VERSION
        or receipt["receipt_type"] != SMOKE_RECEIPT_TYPE
        or receipt["status"] != "pass"
        or receipt["study_id"] != protocol.STUDY_ID
        or receipt["protocol_version"] != protocol.PROTOCOL_VERSION
    ):
        raise SmokeTestError("smoke receipt identity/status differs")
    if not isinstance(receipt["run_id"], str) or controls.SAFE_RUN_ID.fullmatch(receipt["run_id"]) is None:
        raise SmokeTestError("smoke receipt run ID is unsafe")
    if expected_run_id is not None and receipt["run_id"] != expected_run_id:
        raise SmokeTestError("smoke receipt run ID binding differs")
    hash_fields = (
        "plan_manifest_sha256",
        "plan_source_inventory_sha256",
        "smoke_source_sha256",
        "preexecution_authorization_sha256",
        "ownership_receipt_sha256",
        "guest_receipt_sha256",
        "cache_receipt_sha256",
        "campaign_identity_sha256",
    )
    if any(not _is_hex64(receipt[field]) for field in hash_fields):
        raise SmokeTestError("smoke receipt contains a malformed binding hash")
    if expected_plan_hash is not None and receipt["plan_manifest_sha256"] != expected_plan_hash:
        raise SmokeTestError("smoke receipt plan binding differs")
    for field in (
        "campaign_started_at_unix",
        "provider_terminate_at_unix",
        "completed_at_unix",
    ):
        if not _finite_number(receipt[field]):
            raise SmokeTestError("smoke campaign clock is non-finite")
    if not (
        float(receipt["campaign_started_at_unix"])
        <= float(receipt["completed_at_unix"])
        < float(receipt["provider_terminate_at_unix"])
    ):
        raise SmokeTestError("smoke completion is outside the owned campaign")
    if expected_authorization is not None:
        expected = {
            "preexecution_authorization_sha256": expected_authorization.get(
                "receipt_sha256"
            ),
            "plan_manifest_sha256": expected_authorization.get(
                "plan_manifest_sha256"
            ),
            "plan_source_inventory_sha256": expected_authorization.get(
                "plan_source_inventory_sha256"
            ),
            "ownership_receipt_sha256": expected_authorization.get(
                "ownership_receipt_sha256"
            ),
            "guest_receipt_sha256": expected_authorization.get(
                "guest_receipt_sha256"
            ),
            "cache_receipt_sha256": expected_authorization.get(
                "cache_receipt_sha256"
            ),
            "campaign_identity_sha256": expected_authorization.get(
                "campaign_identity_sha256"
            ),
            "campaign_started_at_unix": expected_authorization.get(
                "campaign_started_at_unix"
            ),
            "provider_terminate_at_unix": expected_authorization.get(
                "provider_terminate_at_unix"
            ),
        }
        if any(receipt.get(field) != value for field, value in expected.items()):
            raise SmokeTestError("smoke/pre-execution authorization binding differs")
    expected_relative = (
        f"{protocol.STUDY_SLUG}/{protocol.STUDY_ID}/"
        f"{SMOKE_RECEIPT_SUBDIRECTORY}/{receipt['run_id']}.json"
    )
    if receipt["external_receipt_relative_path"] != expected_relative:
        raise SmokeTestError("smoke receipt external path binding differs")

    binding = receipt["execution_binding"]
    _require_exact_fields(
        binding,
        {
            "backend",
            "provider_gpu_type",
            "provider_gpu_count",
            "model_revision",
            "model_dtype",
            "sae_revision",
            "sae_sha256",
            "j_lens_revision",
            "j_lens_sha256",
            "container_image",
            "public_artifact_rehash_bound",
        },
        "smoke execution binding",
    )
    if (
        binding.get("provider_gpu_type") != runpod_preflight.EXPECTED_GPU_TYPE
        or binding.get("provider_gpu_count") != 1
        or binding.get("model_revision") != protocol.MODEL_SPEC["revision"]
        or binding.get("model_dtype") != protocol.MODEL_SPEC["dtype"]
        or binding.get("sae_revision") != protocol.SAE_SPEC["revision"]
        or binding.get("sae_sha256") != protocol.SAE_SPEC["sha256"]
        or binding.get("j_lens_revision") != protocol.J_LENS_SPEC["revision"]
        or binding.get("j_lens_sha256") != protocol.J_LENS_SPEC["sha256"]
        or binding.get("container_image") != protocol.CONTAINER_IMAGE_SPEC
        or binding.get("backend")
        != "consciousness_sae_realization_validation.runtime.V2Backend"
        or binding.get("public_artifact_rehash_bound") is not True
    ):
        raise SmokeTestError("smoke execution binding differs")

    prompt = _require_exact_fields(
        receipt["prompt_receipt"],
        {
            "prompt_id",
            "prompt_role",
            "prompt_payload_sha256",
            "token_ids",
            "token_ids_sha256",
            "token_count",
            "overlaps_stage_a_or_b",
            "target_prompt",
        },
        "smoke prompt receipt",
    )
    token_ids = prompt.get("token_ids")
    if (
        prompt.get("prompt_id") != SMOKE_PROMPT_ID
        or prompt.get("prompt_role") != "disjoint_mundane_operational_smoke_only"
        or prompt.get("prompt_payload_sha256") != protocol.canonical_sha256(SMOKE_PROMPT)
        or not isinstance(token_ids, list)
        or len(token_ids) < 2
        or any(
            isinstance(token_id, bool)
            or not isinstance(token_id, int)
            or not 0 <= token_id < protocol.VOCAB_SIZE
            for token_id in token_ids
        )
        or prompt.get("token_count") != len(token_ids)
        or prompt.get("token_ids_sha256") != runtime.token_ids_sha256(token_ids)
        or prompt.get("overlaps_stage_a_or_b") is not False
        or prompt.get("target_prompt") is not False
    ):
        raise SmokeTestError("smoke prompt receipt differs")

    edit = _require_exact_fields(
        receipt["edit_contract"],
        {
            "edit_layer",
            "dose_fraction",
            "dose_role",
            "direction_role",
            "direction_seed",
            "unit_direction_sha256",
            "requested_positive_sha256",
            "signed_branch_count",
            "sae_feature_ids",
        },
        "smoke edit contract",
    )
    if (
        edit.get("edit_layer") != SMOKE_EDIT_LAYER
        or edit.get("dose_fraction") != SMOKE_DOSE_FRACTION
        or edit.get("dose_role") != "tiny_operational_diagnostic_only"
        or edit.get("direction_role") != "smoke_only_generic_non_sae_direction"
        or edit.get("direction_seed")
        != protocol.seed64("b200-execution-smoke-generic-direction", SMOKE_EDIT_LAYER)
        or edit.get("signed_branch_count") != 2
        or edit.get("sae_feature_ids") != []
        or not _is_hex64(edit.get("unit_direction_sha256"))
        or not _is_hex64(edit.get("requested_positive_sha256"))
    ):
        raise SmokeTestError("smoke edit contract differs")

    captures = receipt["capture_receipt"]
    if not isinstance(captures, Mapping) or set(captures) != {"clean", "plus", "minus"}:
        raise SmokeTestError("smoke capture receipt differs")
    for branch, row in captures.items():
        _require_exact_fields(
            row,
            {
                "branch",
                "captured_j_layers",
                "captured_j_layer_count",
                "final_state_captured",
                "arc_tensor_sha256",
            },
            f"smoke {branch} capture",
        )
        if (
            row.get("branch") != branch
            or row.get("captured_j_layers") != list(protocol.J_LAYERS)
            or row.get("captured_j_layer_count") != len(protocol.J_LAYERS)
            or row.get("final_state_captured") is not True
            or not _is_hex64(row.get("arc_tensor_sha256"))
        ):
            raise SmokeTestError("smoke 45--78 capture proof differs")

    realization = _require_exact_fields(
        receipt["realization_receipt"],
        {
            "hook_fire_count_plus",
            "hook_fire_count_minus",
            "pre_equals_clean_plus",
            "pre_equals_clean_minus",
            "captured_layer50_equals_pre_plus",
            "captured_layer50_equals_pre_minus",
            "native_post_bytes_exact_plus",
            "native_post_bytes_exact_minus",
            "requested_vector_exact_plus",
            "requested_vector_exact_minus",
            "upstream_45_49_bytes_equal_clean_plus",
            "upstream_45_49_bytes_equal_clean_minus",
            "requested_realized_central_relative_rmse",
            "requested_realized_central_cosine",
            "requested_rms_fraction",
            "realized_rms_fraction",
            "common_mode_to_central_rms",
            "realized_central_sha256",
            "actual_final_central_sha256",
            "finite",
        },
        "smoke realization receipt",
    )
    required_true = (
        "pre_equals_clean_plus",
        "pre_equals_clean_minus",
        "captured_layer50_equals_pre_plus",
        "captured_layer50_equals_pre_minus",
        "native_post_bytes_exact_plus",
        "native_post_bytes_exact_minus",
        "requested_vector_exact_plus",
        "requested_vector_exact_minus",
        "upstream_45_49_bytes_equal_clean_plus",
        "upstream_45_49_bytes_equal_clean_minus",
        "finite",
    )
    if any(realization.get(field) is not True for field in required_true):
        raise SmokeTestError("smoke BF16 realization proof differs")
    if realization.get("hook_fire_count_plus") != 1 or realization.get("hook_fire_count_minus") != 1:
        raise SmokeTestError("smoke hook did not fire exactly once per signed branch")
    for field in (
        "requested_realized_central_relative_rmse",
        "requested_realized_central_cosine",
        "requested_rms_fraction",
        "realized_rms_fraction",
        "common_mode_to_central_rms",
    ):
        if not _finite_number(realization.get(field)):
            raise SmokeTestError("smoke realization metric is non-finite")
    if not _is_hex64(realization.get("realized_central_sha256")) or not _is_hex64(
        realization.get("actual_final_central_sha256")
    ):
        raise SmokeTestError("smoke realization hash is malformed")

    transport = _require_exact_fields(
        receipt["transport_receipt"],
        {
            "transport",
            "transport_count",
            "edit_layer",
            "selected_token_ids",
            "selected_token_count",
            "selected_token_panel_sha256",
            "predicted_final_delta_sha256",
            "actual_final_delta_sha256",
            "residual_delta_cosine",
            "selected_logit_delta_pearson",
            "finite",
        },
        "smoke transport receipt",
    )
    panel = transport.get("selected_token_ids")
    if (
        transport.get("transport") != "real_j"
        or transport.get("transport_count") != 1
        or transport.get("edit_layer") != SMOKE_EDIT_LAYER
        or not isinstance(panel, list)
        or len(panel) != SMOKE_SELECTED_TOKEN_COUNT
        or any(
            isinstance(token_id, bool)
            or not isinstance(token_id, int)
            or not 0 <= token_id < protocol.VOCAB_SIZE
            for token_id in panel
        )
        or len(set(panel)) != SMOKE_SELECTED_TOKEN_COUNT
        or transport.get("selected_token_count") != SMOKE_SELECTED_TOKEN_COUNT
        or transport.get("selected_token_panel_sha256")
        != protocol.canonical_sha256(panel)
        or not _finite_number(transport.get("residual_delta_cosine"))
        or not _finite_number(transport.get("selected_logit_delta_pearson"))
        or not _is_hex64(transport.get("predicted_final_delta_sha256"))
        or not _is_hex64(transport.get("actual_final_delta_sha256"))
        or transport.get("finite") is not True
    ):
        raise SmokeTestError("smoke real-J transport proof differs")

    replay = _require_exact_fields(
        receipt["replay_receipt"],
        {
            "scope",
            "top_k",
            "actual_selected_delta_sha256",
            "actual_selected_delta_replay_sha256",
            "predicted_selected_delta_sha256",
            "predicted_selected_delta_replay_sha256",
            "actual_selected_logits_replay_exact",
            "predicted_selected_logits_replay_exact",
            "actual_top",
            "actual_bottom",
            "predicted_top",
            "predicted_bottom",
            "full_vocabulary_replay_claimed",
            "scientific_replay_claimed",
        },
        "smoke replay receipt",
    )
    if (
        replay.get("scope") != "selected_panel_topk_operational_primitive"
        or replay.get("top_k") != SMOKE_TOP_K
        or replay.get("actual_selected_logits_replay_exact") is not True
        or replay.get("predicted_selected_logits_replay_exact") is not True
        or replay.get("full_vocabulary_replay_claimed") is not False
        or replay.get("scientific_replay_claimed") is not False
    ):
        raise SmokeTestError("smoke replay primitive differs")
    for field in (
        "actual_selected_delta_sha256",
        "actual_selected_delta_replay_sha256",
        "predicted_selected_delta_sha256",
        "predicted_selected_delta_replay_sha256",
    ):
        if not _is_hex64(replay.get(field)):
            raise SmokeTestError("smoke replay hash is malformed")
    panel_set = {int(value) for value in panel}
    for field, largest in (
        ("actual_top", True),
        ("actual_bottom", False),
        ("predicted_top", True),
        ("predicted_bottom", False),
    ):
        _validate_topk_rows(replay.get(field), panel=panel_set, largest=largest)

    if (
        receipt["model_forward_count"] != SMOKE_EXPECTED_MODEL_FORWARD_COUNT
        or receipt["expected_model_forward_count"]
        != SMOKE_EXPECTED_MODEL_FORWARD_COUNT
        or receipt["mundane_smoke_prompt_render_count"] != 1
        or any(
            receipt[field] != 0
            for field in (
                "stage_a_prompt_render_count",
                "stage_b_prompt_render_count",
                "paper_prompt_render_count",
                "target_prompt_render_count",
                "target_feature_vector_count",
                "target_outcome_count",
                "behavioral_outcome_count",
                "scientific_gate_input_count",
                "dose_selection_input_count",
            )
        )
        or receipt["scientific_gate_eligible"] is not False
        or receipt["dose_selection_eligible"] is not False
        or receipt["result_reuse_prohibited"] is not True
        or receipt["prior_outcome_inputs"] != []
    ):
        raise SmokeTestError("smoke non-scientific/target-free boundary differs")
    runtime_metadata = receipt["runtime_metadata"]
    if not isinstance(runtime_metadata, Mapping) or runtime_metadata.get(
        "model_forward_count"
    ) != SMOKE_EXPECTED_MODEL_FORWARD_COUNT:
        raise SmokeTestError("smoke runtime forward count differs")
    hardware = runtime_metadata.get("hardware")
    if not isinstance(hardware, Mapping) or (
        hardware.get("cuda_device_count") != 1
        or "B200" not in str(hardware.get("gpu_name", "")).upper()
    ):
        raise SmokeTestError("smoke runtime is not one observed B200")
    return dict(receipt)


def _write_external_receipt(path: Path, receipt: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    current = Path(path.anchor)
    for part in path.parent.parts[1:]:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise SmokeTestError("smoke receipt parent path is unsafe")
    try:
        runpod_preflight.validate_study_owned_output_tree(path.parent)
    except runpod_preflight.PreflightError as exc:
        raise SmokeTestError(f"smoke receipt directory is unsafe: {exc}") from exc
    if path.exists() or path.is_symlink():
        raise SmokeTestError("refusing to overwrite a smoke receipt")
    partial = path.with_name(path.name + ".partial")
    if partial.exists() or partial.is_symlink():
        raise SmokeTestError("smoke receipt partial path already exists")
    try:
        with partial.open("xb") as handle:
            handle.write(protocol.canonical_json_bytes(dict(receipt)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        loaded = json.loads(partial.read_text(encoding="utf-8"))
        validate_smoke_receipt(loaded)
        runpod_preflight.validate_study_owned_output_tree(path.parent)
        os.replace(partial, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return path
    except BaseException:
        # Preserve a failed partial for diagnosis; it is never accepted by the
        # validator and can never be mistaken for the final external receipt.
        raise


def execute_smoke(
    *,
    plan_dir: Path,
    volume_root: Path,
    volume_id: str,
    run_id: str,
    model_snapshot: Path,
    sae_path: Path,
    j_lens_path: Path,
    hourly_price_usd: float,
    campaign_started_at_unix: float,
    provider_terminate_at_unix: float,
    ownership_receipt_path: Path,
    guest_receipt_path: Path,
    cache_receipt_path: Path,
    preexecution_authorization_path: Path,
) -> Path:
    """Execute exactly one target-free clean/+/- smoke session."""

    _validate_constants()
    plan = runner._validate_plan(plan_dir)
    plan_hash = str(plan["plan_manifest_sha256"])
    source_inventory_hash, smoke_source_hash = _source_binding(plan_dir)
    destination = smoke_receipt_path(
        volume_root, volume_id=volume_id, run_id=run_id
    )
    watchdog = runner.ResourceWatchdog.create(
        hourly_price_usd,
        campaign_started_at_unix=campaign_started_at_unix,
        provider_terminate_at_unix=provider_terminate_at_unix,
    )
    ownership, guest, cache = runner._validate_guest_chain(
        ownership_receipt_path=ownership_receipt_path,
        guest_receipt_path=guest_receipt_path,
        cache_receipt_path=cache_receipt_path,
        volume_id=volume_id,
        model_snapshot=model_snapshot,
        sae_path=sae_path,
        j_lens_path=j_lens_path,
        campaign_started_at_unix=campaign_started_at_unix,
        provider_terminate_at_unix=provider_terminate_at_unix,
    )
    try:
        authorization = preexecution.load_execution_authorization(
            preexecution_authorization_path,
            repo_root=REPO_ROOT,
            plan_dir=plan_dir,
            ownership_receipt=ownership,
            guest_receipt=guest,
            cache_receipt=cache,
        )
    except preexecution.PreexecutionError as exc:
        raise SmokeTestError(f"pre-execution authorization failed: {exc}") from exc
    if (
        authorization["plan_manifest_sha256"] != plan_hash
        or authorization["network_volume_id"] != volume_id
        or authorization["campaign_started_at_unix"] != campaign_started_at_unix
        or authorization["provider_terminate_at_unix"]
        != provider_terminate_at_unix
    ):
        raise SmokeTestError("smoke command differs from pre-execution authorization")
    backend: runtime.V2Backend | None = None
    session: runtime.ArcPromptSession | None = None
    try:
        tokenizer, backend, artifact_records = runner._load_backend(
            model_snapshot=model_snapshot,
            sae_path=sae_path,
            j_lens_path=j_lens_path,
            ownership_receipt_sha256=ownership["receipt_sha256"],
            shadow_layers=(),
        )
        watchdog.check()
        token_ids, prompt_receipt = render_smoke_prompt(tokenizer)
        backend.start_runtime_interval()
        session = backend.prepare_arc(token_ids)
        clean_source = session.clean.residual_by_layer[SMOKE_EDIT_LAYER]
        unit = smoke_direction()
        requested_fp32 = (
            unit * (runtime.tensor_rms(clean_source) * SMOKE_DOSE_FRACTION)
        ).to(dtype=backend.torch.float32).contiguous()
        requested = requested_fp32.to(dtype=backend.torch.bfloat16).contiguous()
        negative = backend.torch.neg(requested).contiguous()
        plus = session.edited(
            SMOKE_EDIT_LAYER,
            requested.to(device=backend.device),
            forward_id=f"{run_id}:{SMOKE_PROMPT_ID}:plus",
        )
        minus = session.edited(
            SMOKE_EDIT_LAYER,
            negative.to(device=backend.device),
            forward_id=f"{run_id}:{SMOKE_PROMPT_ID}:minus",
        )
        watchdog.check()

        capture_receipt = {
            "clean": _capture_summary(session.clean, branch="clean"),
            "plus": _capture_summary(plus, branch="plus"),
            "minus": _capture_summary(minus, branch="minus"),
        }
        values, realized_central, final_central = runtime.realization_metrics(
            clean_source,
            plus,
            minus,
            requested,
            requested_positive_fp32=requested_fp32,
        )
        assert plus.pre_edit is not None and plus.post_edit is not None
        assert minus.pre_edit is not None and minus.post_edit is not None
        assert plus.requested_vector is not None and minus.requested_vector is not None
        realization_receipt = {
            "hook_fire_count_plus": plus.hook_fire_count,
            "hook_fire_count_minus": minus.hook_fire_count,
            "pre_equals_clean_plus": bool(backend.torch.equal(plus.pre_edit, clean_source)),
            "pre_equals_clean_minus": bool(backend.torch.equal(minus.pre_edit, clean_source)),
            "captured_layer50_equals_pre_plus": bool(
                backend.torch.equal(plus.residual_by_layer[SMOKE_EDIT_LAYER], plus.pre_edit)
            ),
            "captured_layer50_equals_pre_minus": bool(
                backend.torch.equal(minus.residual_by_layer[SMOKE_EDIT_LAYER], minus.pre_edit)
            ),
            "native_post_bytes_exact_plus": values["native_post_bytes_exact_plus"],
            "native_post_bytes_exact_minus": values["native_post_bytes_exact_minus"],
            "requested_vector_exact_plus": bool(
                backend.torch.equal(plus.requested_vector, requested)
            ),
            "requested_vector_exact_minus": bool(
                backend.torch.equal(minus.requested_vector, negative)
            ),
            "upstream_45_49_bytes_equal_clean_plus": all(
                backend.torch.equal(
                    plus.residual_by_layer[layer], session.clean.residual_by_layer[layer]
                )
                for layer in range(45, 50)
            ),
            "upstream_45_49_bytes_equal_clean_minus": all(
                backend.torch.equal(
                    minus.residual_by_layer[layer], session.clean.residual_by_layer[layer]
                )
                for layer in range(45, 50)
            ),
            "requested_realized_central_relative_rmse": values[
                "requested_realized_central_relative_rmse"
            ],
            "requested_realized_central_cosine": values[
                "requested_realized_central_cosine"
            ],
            "requested_rms_fraction": values["requested_rms_fraction"],
            "realized_rms_fraction": values["realized_rms_fraction"],
            "common_mode_to_central_rms": values["common_mode_to_central_rms"],
            "realized_central_sha256": runtime.tensor_sha256(realized_central),
            "actual_final_central_sha256": runtime.tensor_sha256(final_central),
            "finite": bool(values["finite"]),
        }
        validate_probe = {field: realization_receipt[field] for field in (
            "pre_equals_clean_plus",
            "pre_equals_clean_minus",
            "captured_layer50_equals_pre_plus",
            "captured_layer50_equals_pre_minus",
            "native_post_bytes_exact_plus",
            "native_post_bytes_exact_minus",
            "requested_vector_exact_plus",
            "requested_vector_exact_minus",
            "upstream_45_49_bytes_equal_clean_plus",
            "upstream_45_49_bytes_equal_clean_minus",
            "finite",
        )}
        if plus.hook_fire_count != 1 or minus.hook_fire_count != 1 or not all(validate_probe.values()):
            raise SmokeTestError("smoke hook/native BF16 realization did not pass")

        selected_ids = smoke_selected_token_panel()
        predicted_final = backend.transport_realized(
            realized_central, layer=SMOKE_EDIT_LAYER, transport="real_j"
        )
        clean_final = session.clean.final_residual.to(device=backend.device).float()
        predicted_logits = (
            backend.selected_logits_from_state(clean_final + predicted_final.float(), selected_ids)
            - backend.selected_logits_from_state(clean_final - predicted_final.float(), selected_ids)
        ) * 0.5
        actual_logits = runner._actual_selected_delta(
            backend, plus, minus, selected_ids
        )
        actual_replay = runner._actual_selected_delta(
            backend, plus, minus, selected_ids
        )
        predicted_replay = (
            backend.selected_logits_from_state(clean_final + predicted_final.float(), selected_ids)
            - backend.selected_logits_from_state(clean_final - predicted_final.float(), selected_ids)
        ) * 0.5
        actual_cpu = actual_logits.detach().to(device="cpu").contiguous()
        actual_replay_cpu = actual_replay.detach().to(device="cpu").contiguous()
        predicted_cpu = predicted_logits.detach().to(device="cpu").contiguous()
        predicted_replay_cpu = predicted_replay.detach().to(device="cpu").contiguous()
        actual_replay_exact = bool(backend.torch.equal(actual_cpu, actual_replay_cpu))
        predicted_replay_exact = bool(
            backend.torch.equal(predicted_cpu, predicted_replay_cpu)
        )
        if not actual_replay_exact or not predicted_replay_exact:
            raise SmokeTestError("selected-logit replay primitive is not byte-exact")
        transport_receipt = {
            "transport": "real_j",
            "transport_count": 1,
            "edit_layer": SMOKE_EDIT_LAYER,
            "selected_token_ids": list(selected_ids),
            "selected_token_count": len(selected_ids),
            "selected_token_panel_sha256": protocol.canonical_sha256(list(selected_ids)),
            "predicted_final_delta_sha256": runtime.tensor_sha256(predicted_final),
            "actual_final_delta_sha256": runtime.tensor_sha256(final_central),
            "residual_delta_cosine": runtime.cosine(final_central, predicted_final),
            "selected_logit_delta_pearson": runtime.pearson(actual_cpu, predicted_cpu),
            "finite": bool(
                backend.torch.isfinite(predicted_final).all()
                and backend.torch.isfinite(actual_cpu).all()
                and backend.torch.isfinite(predicted_cpu).all()
            ),
        }
        replay_receipt = {
            "scope": "selected_panel_topk_operational_primitive",
            "top_k": SMOKE_TOP_K,
            "actual_selected_delta_sha256": runtime.tensor_sha256(actual_cpu),
            "actual_selected_delta_replay_sha256": runtime.tensor_sha256(actual_replay_cpu),
            "predicted_selected_delta_sha256": runtime.tensor_sha256(predicted_cpu),
            "predicted_selected_delta_replay_sha256": runtime.tensor_sha256(
                predicted_replay_cpu
            ),
            "actual_selected_logits_replay_exact": actual_replay_exact,
            "predicted_selected_logits_replay_exact": predicted_replay_exact,
            "actual_top": _stable_panel_topk(actual_cpu, selected_ids, largest=True),
            "actual_bottom": _stable_panel_topk(actual_cpu, selected_ids, largest=False),
            "predicted_top": _stable_panel_topk(predicted_cpu, selected_ids, largest=True),
            "predicted_bottom": _stable_panel_topk(predicted_cpu, selected_ids, largest=False),
            "full_vocabulary_replay_claimed": False,
            "scientific_replay_claimed": False,
        }
        runtime_metadata = backend.runtime_metadata()
        if runtime_metadata.get("model_forward_count") != SMOKE_EXPECTED_MODEL_FORWARD_COUNT:
            raise SmokeTestError(
                "smoke model-forward count differs from prefix+clean+signed-pair contract"
            )
        watchdog.check()
        external_relative = destination.relative_to(
            controls.require_volume_root(volume_root, volume_id=volume_id)
        ).as_posix()
        core = {
            "schema_version": SMOKE_SCHEMA_VERSION,
            "receipt_type": SMOKE_RECEIPT_TYPE,
            "status": "pass",
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "run_id": run_id,
            "plan_manifest_sha256": plan_hash,
            "plan_source_inventory_sha256": source_inventory_hash,
            "smoke_source_sha256": smoke_source_hash,
            "preexecution_authorization_sha256": authorization["receipt_sha256"],
            "ownership_receipt_sha256": ownership["receipt_sha256"],
            "guest_receipt_sha256": guest["receipt_sha256"],
            "cache_receipt_sha256": cache["receipt_sha256"],
            "campaign_identity_sha256": authorization[
                "campaign_identity_sha256"
            ],
            "campaign_started_at_unix": campaign_started_at_unix,
            "provider_terminate_at_unix": provider_terminate_at_unix,
            "completed_at_unix": time.time(),
            "external_receipt_relative_path": external_relative,
            "execution_binding": {
                "backend": "consciousness_sae_realization_validation.runtime.V2Backend",
                "provider_gpu_type": ownership["gpu_type"],
                "provider_gpu_count": ownership["gpu_count"],
                "model_revision": protocol.MODEL_SPEC["revision"],
                "model_dtype": protocol.MODEL_SPEC["dtype"],
                "sae_revision": protocol.SAE_SPEC["revision"],
                "sae_sha256": artifact_records["sae"]["sha256"],
                "j_lens_revision": protocol.J_LENS_SPEC["revision"],
                "j_lens_sha256": artifact_records["j_lens"]["sha256"],
                "container_image": protocol.CONTAINER_IMAGE_SPEC,
                "public_artifact_rehash_bound": True,
            },
            "prompt_receipt": prompt_receipt,
            "edit_contract": {
                "edit_layer": SMOKE_EDIT_LAYER,
                "dose_fraction": SMOKE_DOSE_FRACTION,
                "dose_role": "tiny_operational_diagnostic_only",
                "direction_role": "smoke_only_generic_non_sae_direction",
                "direction_seed": protocol.seed64(
                    "b200-execution-smoke-generic-direction", SMOKE_EDIT_LAYER
                ),
                "unit_direction_sha256": runtime.tensor_sha256(unit),
                "requested_positive_sha256": runtime.tensor_sha256(requested),
                "signed_branch_count": 2,
                "sae_feature_ids": [],
            },
            "capture_receipt": capture_receipt,
            "realization_receipt": realization_receipt,
            "transport_receipt": transport_receipt,
            "replay_receipt": replay_receipt,
            "runtime_metadata": runtime_metadata,
            "resource": watchdog.receipt(),
            "model_forward_count": int(runtime_metadata["model_forward_count"]),
            "expected_model_forward_count": SMOKE_EXPECTED_MODEL_FORWARD_COUNT,
            "mundane_smoke_prompt_render_count": 1,
            "stage_a_prompt_render_count": 0,
            "stage_b_prompt_render_count": 0,
            "paper_prompt_render_count": 0,
            "target_prompt_render_count": 0,
            "target_feature_vector_count": 0,
            "target_outcome_count": 0,
            "behavioral_outcome_count": 0,
            "scientific_gate_input_count": 0,
            "dose_selection_input_count": 0,
            "scientific_gate_eligible": False,
            "dose_selection_eligible": False,
            "result_reuse_prohibited": True,
            "prior_outcome_inputs": [],
        }
        receipt = _seal(core)
        validate_smoke_receipt(
            receipt,
            expected_plan_hash=plan_hash,
            expected_run_id=run_id,
            expected_authorization=authorization,
        )
        return _write_external_receipt(destination, receipt)
    finally:
        if session is not None:
            session.close()
        if backend is not None:
            backend.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--volume-root", type=Path, required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model-snapshot", type=Path, required=True)
    parser.add_argument("--sae-path", type=Path, required=True)
    parser.add_argument("--j-lens-path", type=Path, required=True)
    parser.add_argument("--hourly-price-usd", type=float, required=True)
    parser.add_argument("--campaign-started-at-unix", type=float, required=True)
    parser.add_argument("--provider-terminate-at-unix", type=float, required=True)
    parser.add_argument("--ownership-receipt", type=Path, required=True)
    parser.add_argument("--guest-receipt", type=Path, required=True)
    parser.add_argument("--cache-receipt", type=Path, required=True)
    parser.add_argument("--preexecution-authorization", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = execute_smoke(
        plan_dir=args.plan_dir,
        volume_root=args.volume_root,
        volume_id=args.volume_id,
        run_id=args.run_id,
        model_snapshot=args.model_snapshot,
        sae_path=args.sae_path,
        j_lens_path=args.j_lens_path,
        hourly_price_usd=args.hourly_price_usd,
        campaign_started_at_unix=args.campaign_started_at_unix,
        provider_terminate_at_unix=args.provider_terminate_at_unix,
        ownership_receipt_path=args.ownership_receipt,
        guest_receipt_path=args.guest_receipt,
        cache_receipt_path=args.cache_receipt,
        preexecution_authorization_path=args.preexecution_authorization,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
