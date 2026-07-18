#!/usr/bin/env python3
"""Execute and seal the target-blind semantic positive control.

The control uses only the frozen neutral prompt packet.  For each prompt it
caches every rendered token except the final generation-prompt token, then
forks that exact cache into one clean branch and three single-coordinate
layer-50 edits.  The edit is ``0.5 * SAE_decoder[:, feature_id]`` at the final
input position.  Real-J readouts at layers 51:78 and actual next-token logits
are retained along with every source residual on the external study volume.
No confirmatory target prompt is imported or rendered here.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_changepoint import paths  # noqa: E402
from experiments.consciousness_sae_changepoint.calibrate import (  # noqa: E402
    validate_artifact_receipt,
    validate_calibration_receipt,
)
from experiments.consciousness_sae_changepoint.protocol import (  # noqa: E402
    MODEL_WIDTH,
    PROTOCOL_VERSION,
    SAE_FILE_SHA256,
    SAE_FILENAME,
    SAE_ID,
    SAE_LAYER,
    SAE_REVISION,
    STUDY_ID,
    TARGET_FEATURE_IDS,
    canonical_json_bytes,
    sha256_file,
    stable_id,
)
from experiments.consciousness_sae_changepoint.run import (  # noqa: E402
    PinnedRuntime,
    TraceSource,
)
from experiments.consciousness_sae_changepoint.runtime_core import (  # noqa: E402
    Layer50SwitchHook,
    cache_tensor_sha256,
    clone_kv_cache,
    tensor_sha256,
)
from experiments.consciousness_sae_changepoint.semantic_controls import (  # noqa: E402
    DESCRIPTION_EXCLUSION_PATTERN_TEXT,
    DESCRIPTION_NORMALIZATION,
    DESCRIPTION_PATTERN_FLAGS,
    DESCRIPTION_PATTERN_TEXT,
    N_SEMANTIC_CONTROLS,
    SEMANTIC_CONTROL_COEFFICIENT,
    SEMANTIC_CONTROL_LAYERS,
    SEMANTIC_CONTROL_PROMPTS,
    SEMANTIC_CONTROL_SCHEMA_VERSION,
    _tensor_eligibility_for_matches,
    analyze_semantic_control_scores,
    select_semantic_controls,
    sha256_json,
)
from experiments.consciousness_sae_changepoint.storage import (  # noqa: E402
    RunTransaction,
    verify_completed_block,
    verify_completed_run,
)


SEMANTIC_CONTROL_RUN_SCHEMA_VERSION = 1
SELECTION_FILENAME = "semantic_control_selection_receipt.json"
ARTIFACT_FILENAME = "artifact_receipt.json"
CALIBRATION_FILENAME = "calibration_receipt.json"
EXPLICIT_TOKEN_LABELS = (
    "explicit_conscious",
    "explicit_consciousness",
    "explicit_sentient",
)
HEX = frozenset("0123456789abcdef")


class SemanticControlRunError(RuntimeError):
    """The target-blind positive-control contract was violated."""


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def _without_hash(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result.pop(field, None)
    return result


def _load_completed_receipt(
    path: Path,
    *,
    root: Path,
    expected_filename: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = path.expanduser().resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SemanticControlRunError("gate receipt is outside the external root") from exc
    if resolved.name != expected_filename:
        raise SemanticControlRunError(f"gate receipt filename differs: {resolved.name}")
    try:
        sealed = verify_completed_run(resolved.parent)
    except Exception as exc:
        raise SemanticControlRunError(
            f"{expected_filename} is not inside a verified completed transaction"
        ) from exc
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SemanticControlRunError(f"invalid {expected_filename}") from exc
    if not isinstance(payload, dict):
        raise SemanticControlRunError(f"{expected_filename} is not a JSON object")
    return payload, {**sealed, "file_sha256": sha256_file(resolved)}


def validate_selection_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_volume_id: str,
    calibration_receipt_sha256: str,
    calibration_file_sha256: str,
    calibration_manifest_sha256: str,
) -> dict[str, Any]:
    """Validate the complete mechanical-selection record without trusting it."""

    exact = {
        "schema_version": SEMANTIC_CONTROL_SCHEMA_VERSION,
        "status": "pass",
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "outcome_blind": True,
        "target_outcomes_opened": False,
        "prior_outcome_inputs": [],
        "expected_volume_id": expected_volume_id,
        "sae_file_sha256": SAE_FILE_SHA256,
        "calibration_receipt_embedded_sha256": calibration_receipt_sha256,
        "calibration_receipt_file_sha256": calibration_file_sha256,
        "calibration_manifest_sha256": calibration_manifest_sha256,
    }
    for field, expected in exact.items():
        if receipt.get(field) != expected:
            raise SemanticControlRunError(f"selection receipt {field} differs")
    embedded = receipt.get("receipt_sha256")
    if not _is_sha256(embedded) or sha256_json(
        _without_hash(receipt, "receipt_sha256")
    ) != embedded:
        raise SemanticControlRunError("selection receipt canonical hash differs")

    selection = receipt.get("selection")
    if not isinstance(selection, Mapping):
        raise SemanticControlRunError("selection payload is missing")
    if selection.get("algorithm") != (
        "ascending_feature_id_after_regex_exclusions_and_tensor_screen_v1"
    ):
        raise SemanticControlRunError("selection algorithm differs")
    for field, expected in (
        ("unicode_normalization", DESCRIPTION_NORMALIZATION),
        ("regex", DESCRIPTION_PATTERN_TEXT),
        ("exclusion_regex", DESCRIPTION_EXCLUSION_PATTERN_TEXT),
        ("regex_flags", DESCRIPTION_PATTERN_FLAGS),
        ("excluded_target_feature_ids", list(TARGET_FEATURE_IDS)),
        ("n_required", N_SEMANTIC_CONTROLS),
    ):
        if selection.get(field) != expected:
            raise SemanticControlRunError(f"selection rule {field} differs")
    selection_hash = selection.get("selection_sha256")
    if not _is_sha256(selection_hash) or sha256_json(
        _without_hash(selection, "selection_sha256")
    ) != selection_hash:
        raise SemanticControlRunError("selection decision hash differs")
    selected = selection.get("selected")
    ids = selection.get("selected_feature_ids")
    if not isinstance(selected, list) or not isinstance(ids, list):
        raise SemanticControlRunError("selected semantic controls are missing")
    normalized_ids = [int(value) for value in ids]
    if (
        len(normalized_ids) != N_SEMANTIC_CONTROLS
        or normalized_ids != sorted(set(normalized_ids))
        or set(normalized_ids) & set(TARGET_FEATURE_IDS)
        or normalized_ids != [int(row.get("feature_id", -1)) for row in selected]
    ):
        raise SemanticControlRunError("selected semantic-control IDs differ")
    for row in selected:
        if (
            not isinstance(row, Mapping)
            or row.get("eligible") is not True
            or row.get("reason") != "selected"
            or not isinstance(row.get("description"), str)
            or not _is_sha256(row.get("description_sha256"))
            or not math.isfinite(float(row.get("decoder_norm", float("nan"))))
            or float(row["decoder_norm"]) <= 0.0
        ):
            raise SemanticControlRunError("selected semantic-control row is invalid")
    return {
        "status": "pass",
        "receipt_sha256": embedded,
        "selection_sha256": selection_hash,
        "selected_feature_ids": normalized_ids,
    }


def _token_ids(tokenized: Any) -> list[int]:
    if isinstance(tokenized, Mapping):
        tokenized = tokenized.get("input_ids")
    elif hasattr(tokenized, "input_ids"):
        tokenized = tokenized.input_ids
    if hasattr(tokenized, "tolist"):
        tokenized = tokenized.tolist()
    if isinstance(tokenized, list) and tokenized and isinstance(tokenized[0], list):
        if len(tokenized) != 1:
            raise SemanticControlRunError("tokenizer returned a non-singleton batch")
        tokenized = tokenized[0]
    if not isinstance(tokenized, (list, tuple)):
        raise SemanticControlRunError("tokenizer returned no token sequence")
    result = [int(value) for value in tokenized]
    if len(result) < 2:
        raise SemanticControlRunError("rendered neutral prompt is too short to fork")
    return result


def _reconstruct_sealed_selection(
    *,
    cache_dir: Path,
    selection_directory: Path,
    expected_selection: Mapping[str, Any],
    matched_feature_ids: Sequence[int],
) -> None:
    """Re-run the mechanical selector from the sealed labels and pinned SAE."""

    import torch
    from huggingface_hub import hf_hub_download

    labels_path = selection_directory / "labels.json"
    try:
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SemanticControlRunError("sealed public-label snapshot is invalid") from exc
    if not isinstance(labels, list):
        raise SemanticControlRunError("sealed public-label snapshot is not a list")
    sae_path = Path(
        hf_hub_download(
            repo_id=SAE_ID,
            filename=SAE_FILENAME,
            revision=SAE_REVISION,
            cache_dir=cache_dir,
            local_files_only=True,
            token=os.environ.get("HF_TOKEN")
            or os.environ.get("HUGGING_FACE_HUB_TOKEN"),
        )
    )
    if sha256_file(sae_path) != SAE_FILE_SHA256:
        raise SemanticControlRunError("live SAE file differs during selection replay")
    state = torch.load(sae_path, map_location="cpu", weights_only=True, mmap=True)
    eligibility = _tensor_eligibility_for_matches(labels, state)
    reconstructed = select_semantic_controls(
        labels,
        matched_feature_ids=matched_feature_ids,
        tensor_eligibility=eligibility,
    )
    if canonical_json_bytes(reconstructed) != canonical_json_bytes(expected_selection):
        raise SemanticControlRunError(
            "sealed semantic-control selection does not reconstruct from labels and SAE"
        )
    del state


def _explicit_score(labels: Sequence[str], values: Sequence[float]) -> float:
    if len(labels) != len(values) or len(labels) != len(set(labels)):
        raise SemanticControlRunError("selected token panel is malformed")
    panel = {str(label): float(value) for label, value in zip(labels, values)}
    if any(label not in panel or not math.isfinite(panel[label]) for label in EXPLICIT_TOKEN_LABELS):
        raise SemanticControlRunError("explicit consciousness token panel is incomplete")
    return sum(panel[label] for label in EXPLICIT_TOKEN_LABELS) / len(
        EXPLICIT_TOKEN_LABELS
    )


def _trace_j_scores(
    runtime: PinnedRuntime, sources: Sequence[TraceSource]
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    source_by_id = {str(source.row["row_id"]): source for source in sources}
    readout_rows = runtime.selected_jlens_readouts(sources)
    scores: dict[str, float] = {}
    for readout in readout_rows:
        source = source_by_id[str(readout["source_row_id"])]
        layer = source.row.get("j_map_layer")
        if (
            layer in SEMANTIC_CONTROL_LAYERS
            and source.row.get("capture_position") == "fork_token"
            and source.row.get("state") == "post_block"
        ):
            key = str(int(layer))
            if key in scores:
                raise SemanticControlRunError(f"duplicate J score at layer {key}")
            scores[key] = _explicit_score(
                readout["token_labels"], readout["real_j_scores"]
            )
    if set(scores) != {str(layer) for layer in SEMANTIC_CONTROL_LAYERS}:
        raise SemanticControlRunError("post-intervention J trajectory is incomplete")
    return scores, readout_rows


def _run_traced_branch(
    runtime: PinnedRuntime,
    *,
    input_ids: Any,
    base_cache: Any,
    parent_cache_sha256: str,
    branch: str,
    vector: Any | None,
    prompt_id: str,
    block_id: str,
    run_id: str,
    binding_hashes: Mapping[str, str],
) -> dict[str, Any]:
    cache = clone_kv_cache(base_cache)
    if cache_tensor_sha256(cache) != parent_cache_sha256:
        raise SemanticControlRunError("forked cache differs before a control branch")
    vector_sha256 = (
        tensor_sha256(vector)
        if vector is not None
        else sha256_json({"role": "clean", "width": MODEL_WIDTH, "dtype": "bfloat16"})
    )
    condition_key = stable_id(
        "semantic-control-condition", prompt_id, branch, vector_sha256, length=32
    )
    forward_id = stable_id(
        "semantic-control-forward", run_id, prompt_id, branch, length=32
    )
    runtime.set_trace_binding(
        {
            "plan_hash": binding_hashes["plan_hash"],
            "run_id": run_id,
            "block_id": block_id,
            "prefix_id": prompt_id,
            "stage": "target_blind_semantic_positive_control",
            "artifact_receipt_sha256": binding_hashes["artifact_receipt_sha256"],
            "calibration_receipt_sha256": binding_hashes[
                "calibration_receipt_sha256"
            ],
            "acceptance_receipt_sha256": binding_hashes[
                "selection_receipt_sha256"
            ],
        }
    )
    switch = None
    if vector is not None:
        switch = Layer50SwitchHook(vector, capture_to_cpu=True).register(
            runtime.model.model.layers[SAE_LAYER]
        )
        with switch:
            switch.arm([True], forward_id=forward_id, event_time=None)
            traced = runtime.traced_forward(
                input_ids,
                past_key_values=cache,
                switch=switch,
                forward_id=forward_id,
                event_time=None,
                positions={"fork_token": 0},
                base_metadata={
                    "prefix_id": prompt_id,
                    "branch": branch,
                    "condition_key": condition_key,
                    "condition_name": branch,
                    "intervention_vector_sha256": vector_sha256,
                    "parent_cache_sha256": parent_cache_sha256,
                    "paired_rng_sha256": None,
                },
            )
    else:
        traced = runtime.traced_forward(
            input_ids,
            past_key_values=cache,
            switch=None,
            forward_id=forward_id,
            event_time=None,
            positions={"fork_token": 0},
            base_metadata={
                "prefix_id": prompt_id,
                "branch": branch,
                "condition_key": condition_key,
                "condition_name": branch,
                "intervention_vector_sha256": vector_sha256,
                "parent_cache_sha256": parent_cache_sha256,
                "paired_rng_sha256": None,
            },
        )
    if switch is not None:
        switch.validate_complete(expected_calls=1)
        if switch.telemetry()["unconsumed_captures"] != 0:
            raise SemanticControlRunError("semantic-control hook capture was not consumed")
        hook_telemetry = switch.telemetry()
    else:
        hook_telemetry = {
            "registration_count": 0,
            "hook_call_count": 0,
            "removal_count": 0,
            "selected_position_count": 0,
            "unconsumed_captures": 0,
            "call_receipts": [],
        }
    j_scores, readouts = _trace_j_scores(runtime, traced.sources)
    actual = traced.selected_actual_logits["fork_token"]
    actual_score = _explicit_score(runtime.selected_token_labels, actual)
    logits = traced.output.logits[0, 0].detach()
    result = {
        "branch": branch,
        "condition_key": condition_key,
        "vector_sha256": vector_sha256,
        "parent_cache_sha256": parent_cache_sha256,
        "output_cache_sha256": cache_tensor_sha256(traced.output.past_key_values),
        "full_actual_logits_sha256": tensor_sha256(logits),
        "selected_token_ids": list(runtime.selected_token_ids),
        "selected_token_labels": list(runtime.selected_token_labels),
        "selected_actual_logits": [float(value) for value in actual],
        "explicit_actual_score": actual_score,
        "explicit_real_j_by_layer": j_scores,
        "j_readouts": readouts,
        "hook_telemetry": hook_telemetry,
        "sources": traced.sources,
    }
    del logits, traced, cache
    runtime.torch.cuda.empty_cache()
    return result


def _run_prompt(
    runtime: PinnedRuntime,
    *,
    prompt: Mapping[str, str],
    feature_ids: Sequence[int],
    run_id: str,
    block_id: str,
    binding_hashes: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[TraceSource], dict[str, Any]]:
    torch = runtime.torch
    prompt_id = str(prompt["prompt_id"])
    rendered = runtime.tokenizer.apply_chat_template(
        [{"role": "user", "content": str(prompt["text"])}],
        add_generation_prompt=True,
        tokenize=True,
    )
    ids = _token_ids(rendered)
    prefix = torch.tensor([ids[:-1]], device="cuda", dtype=torch.long)
    fork_token = torch.tensor([[ids[-1]]], device="cuda", dtype=torch.long)
    prefill = runtime.plain_forward(prefix)
    base_cache = prefill.past_key_values
    parent_cache_sha256 = cache_tensor_sha256(base_cache)
    del prefill, prefix

    clean = _run_traced_branch(
        runtime,
        input_ids=fork_token,
        base_cache=base_cache,
        parent_cache_sha256=parent_cache_sha256,
        branch="clean",
        vector=None,
        prompt_id=prompt_id,
        block_id=block_id,
        run_id=run_id,
        binding_hashes=binding_hashes,
    )
    score_rows: list[dict[str, Any]] = []
    sources = list(clean["sources"])
    branch_receipts = [{key: value for key, value in clean.items() if key != "sources"}]
    clean_pre = next(
        source
        for source in clean["sources"]
        if source.row["layer_state"] == "50_pre"
    )
    for feature_id in feature_ids:
        vector = (
            runtime.sae_decoder[:, int(feature_id)]
            .to(device="cuda", dtype=torch.bfloat16)
            .mul(SEMANTIC_CONTROL_COEFFICIENT)
        )
        branch = f"feature_{int(feature_id)}_plus_0p5"
        edited = _run_traced_branch(
            runtime,
            input_ids=fork_token,
            base_cache=base_cache,
            parent_cache_sha256=parent_cache_sha256,
            branch=branch,
            vector=vector,
            prompt_id=prompt_id,
            block_id=block_id,
            run_id=run_id,
            binding_hashes=binding_hashes,
        )
        edited_pre = next(
            source
            for source in edited["sources"]
            if source.row["layer_state"] == "50_pre"
        )
        if tensor_sha256(edited_pre.residual) != tensor_sha256(clean_pre.residual):
            raise SemanticControlRunError(
                "clean and edited branches differ before the layer-50 edit"
            )
        score_rows.append(
            {
                "feature_id": int(feature_id),
                "prompt_id": prompt_id,
                "clean_explicit_j_by_layer": clean["explicit_real_j_by_layer"],
                "edited_explicit_j_by_layer": edited["explicit_real_j_by_layer"],
                "clean_explicit_final": clean["explicit_actual_score"],
                "edited_explicit_final": edited["explicit_actual_score"],
            }
        )
        sources.extend(edited["sources"])
        branch_receipts.append(
            {key: value for key, value in edited.items() if key != "sources"}
        )
        del edited, vector
    del base_cache, fork_token, clean
    runtime.torch.cuda.empty_cache()
    metadata = {
        "prompt_id": prompt_id,
        "prompt_text_sha256": sha256_json(str(prompt["text"])),
        "rendered_token_count": len(ids),
        "rendered_token_ids_sha256": sha256_json(ids),
        "cached_prefix_token_count": len(ids) - 1,
        "fork_token_id_sha256": sha256_json([ids[-1]]),
        "parent_cache_sha256": parent_cache_sha256,
        "branch_receipts": branch_receipts,
    }
    return score_rows, sources, metadata


def validate_control_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if (
        receipt.get("schema_version") != SEMANTIC_CONTROL_RUN_SCHEMA_VERSION
        or receipt.get("study_id") != STUDY_ID
        or receipt.get("protocol_version") != PROTOCOL_VERSION
        or receipt.get("outcome_blind") is not True
        or receipt.get("target_outcomes_opened") is not False
        or receipt.get("prior_outcome_inputs") != []
    ):
        raise SemanticControlRunError("semantic-control receipt identity differs")
    embedded = receipt.get("receipt_sha256")
    if not _is_sha256(embedded) or sha256_json(
        _without_hash(receipt, "receipt_sha256")
    ) != embedded:
        raise SemanticControlRunError("semantic-control receipt hash differs")
    rows = receipt.get("score_rows")
    features = receipt.get("selected_feature_ids")
    if not isinstance(rows, list) or not isinstance(features, list):
        raise SemanticControlRunError("semantic-control score payload is missing")
    reconstructed = analyze_semantic_control_scores(
        rows, selected_feature_ids=[int(value) for value in features]
    )
    if reconstructed != receipt.get("analysis"):
        raise SemanticControlRunError("semantic-control analysis reconstruction differs")
    if receipt.get("status") != reconstructed["status"]:
        raise SemanticControlRunError("semantic-control status differs")
    return {
        "status": receipt["status"],
        "passed": reconstructed["passed"],
        "receipt_sha256": embedded,
    }


def run(
    *,
    cache_dir: Path,
    artifact_receipt_path: Path,
    calibration_receipt_path: Path,
    selection_receipt_path: Path,
    artifact_root: Path | None,
    volume_id: str,
    run_id: str,
) -> dict[str, Any]:
    root = paths.require_external_artifact_root(
        artifact_root, expected_volume_id=volume_id, write_read_probe=True
    )
    cache = cache_dir.expanduser().resolve(strict=True)
    try:
        cache.relative_to(root)
    except ValueError as exc:
        raise SemanticControlRunError("model cache is outside the external root") from exc
    artifact, artifact_seal = _load_completed_receipt(
        artifact_receipt_path, root=root, expected_filename=ARTIFACT_FILENAME
    )
    calibration, calibration_seal = _load_completed_receipt(
        calibration_receipt_path, root=root, expected_filename=CALIBRATION_FILENAME
    )
    selection, selection_seal = _load_completed_receipt(
        selection_receipt_path, root=root, expected_filename=SELECTION_FILENAME
    )
    artifact_hash = validate_artifact_receipt(
        artifact, expected_volume_id=volume_id
    )
    calibration_valid = validate_calibration_receipt(calibration)
    public = calibration["public_sources"]
    if (
        public["artifact_receipt_embedded_sha256"] != artifact_hash
        or public["artifact_receipt_file_sha256"] != artifact_seal["file_sha256"]
    ):
        raise SemanticControlRunError("calibration is not bound to the artifact receipt")
    selection_valid = validate_selection_receipt(
        selection,
        expected_volume_id=volume_id,
        calibration_receipt_sha256=calibration_valid["receipt_sha256"],
        calibration_file_sha256=calibration_seal["file_sha256"],
        calibration_manifest_sha256=calibration_seal["manifest_sha256"],
    )
    semantic_source = (
        REPO_ROOT / "experiments/consciousness_sae_changepoint/semantic_controls.py"
    )
    if selection.get("source_file_sha256") != sha256_file(semantic_source):
        raise SemanticControlRunError("selection source changed after the sealed snapshot")
    _reconstruct_sealed_selection(
        cache_dir=cache,
        selection_directory=selection_receipt_path.expanduser().resolve(strict=True).parent,
        expected_selection=selection["selection"],
        matched_feature_ids=list(calibration_valid["matched_feature_map"].values()),
    )
    spec = {
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "role": "target_blind_semantic_positive_control",
        "selected_feature_ids": selection_valid["selected_feature_ids"],
        "selection_sha256": selection_valid["selection_sha256"],
        "coefficient": SEMANTIC_CONTROL_COEFFICIENT,
        "injection": "0.5 * SAE_decoder[:, feature_id] at layer-50 output",
        "fork": "cache all but final rendered generation-prompt token",
        "capture_layers": list(SEMANTIC_CONTROL_LAYERS),
        "prompt_packet_sha256": sha256_json(list(SEMANTIC_CONTROL_PROMPTS)),
        "analysis_function_source_sha256": sha256_file(semantic_source),
    }
    plan_hash = sha256_json(spec)
    transaction = RunTransaction.start(
        phase="calibration",
        run_id=run_id,
        artifact_root=root,
        expected_volume_id=volume_id,
        metadata={
            **spec,
            "plan_hash": plan_hash,
            "outcome_blind": True,
            "target_outcomes_opened": False,
            "artifact_manifest_sha256": artifact_seal["manifest_sha256"],
            "calibration_manifest_sha256": calibration_seal["manifest_sha256"],
            "selection_manifest_sha256": selection_seal["manifest_sha256"],
        },
    )
    runtime = PinnedRuntime(cache, artifact_receipt=artifact)
    if tuple(runtime.selected_token_labels) != (
        "yes",
        "no",
        *EXPLICIT_TOKEN_LABELS,
    ):
        raise SemanticControlRunError("frozen five-token readout panel is unavailable")
    binding_hashes = {
        "plan_hash": plan_hash,
        "artifact_receipt_sha256": artifact_hash,
        "calibration_receipt_sha256": calibration_valid["receipt_sha256"],
        "selection_receipt_sha256": selection_valid["receipt_sha256"],
    }
    all_scores: list[dict[str, Any]] = []
    block_receipts: list[dict[str, Any]] = []
    for prompt in SEMANTIC_CONTROL_PROMPTS:
        prompt_id = str(prompt["prompt_id"])
        block_id = stable_id("semantic-control-block", prompt_id, length=24)
        block = transaction.begin_block(block_id)
        score_rows, sources, metadata = _run_prompt(
            runtime,
            prompt=prompt,
            feature_ids=selection_valid["selected_feature_ids"],
            run_id=run_id,
            block_id=block_id,
            binding_hashes=binding_hashes,
        )
        residuals = runtime.torch.stack([source.residual for source in sources])
        shard = block.write_source_shard(
            "semantic-control-sources",
            residuals,
            [source.row for source in sources],
        )
        block.write_json("prompt_receipt.json", metadata)
        block.write_json("score_rows.json", score_rows)
        completed_block = block.complete(
            metadata={
                "prompt_id": prompt_id,
                "score_rows_sha256": sha256_json(score_rows),
                "source_shard_sha256": shard.residual_sha256,
                "outcome_blind": True,
            }
        )
        all_scores.extend(score_rows)
        block_receipts.append(
            {
                "block_id": block_id,
                "prompt_id": prompt_id,
                "manifest_sha256": verify_completed_block(completed_block)[
                    "manifest_sha256"
                ],
                "score_rows_sha256": sha256_json(score_rows),
                "source_rows": len(sources),
                "source_residual_sha256": shard.residual_sha256,
            }
        )
        del residuals, sources
        runtime.torch.cuda.empty_cache()
    analysis = analyze_semantic_control_scores(
        all_scores,
        selected_feature_ids=selection_valid["selected_feature_ids"],
    )
    receipt: dict[str, Any] = {
        "schema_version": SEMANTIC_CONTROL_RUN_SCHEMA_VERSION,
        "status": analysis["status"],
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "outcome_blind": True,
        "target_outcomes_opened": False,
        "prior_outcome_inputs": [],
        "expected_volume_id": volume_id,
        "run_id": run_id,
        "plan_hash": plan_hash,
        "spec": spec,
        "artifact_receipt_sha256": artifact_hash,
        "artifact_manifest_sha256": artifact_seal["manifest_sha256"],
        "calibration_receipt_sha256": calibration_valid["receipt_sha256"],
        "calibration_manifest_sha256": calibration_seal["manifest_sha256"],
        "selection_receipt_sha256": selection_valid["receipt_sha256"],
        "selection_manifest_sha256": selection_seal["manifest_sha256"],
        "selected_feature_ids": selection_valid["selected_feature_ids"],
        "selected_token_ids": list(runtime.selected_token_ids),
        "selected_token_labels": list(runtime.selected_token_labels),
        "score_rows": all_scores,
        "score_rows_sha256": sha256_json(all_scores),
        "block_receipts": block_receipts,
        "block_receipts_sha256": sha256_json(block_receipts),
        "analysis": analysis,
        "source_file_sha256": sha256_file(Path(__file__)),
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    validate_control_receipt(receipt)
    transaction.write_json("semantic_positive_control_receipt.json", receipt)
    completed = transaction.complete(
        metadata={
            "study_id": STUDY_ID,
            "status": receipt["status"],
            "receipt_sha256": receipt["receipt_sha256"],
            "selected_feature_ids": selection_valid["selected_feature_ids"],
            "outcome_blind": True,
        }
    )
    sealed = verify_completed_run(completed)
    return {
        "status": receipt["status"],
        "passed": analysis["passed"],
        "receipt_sha256": receipt["receipt_sha256"],
        "completed_directory": completed.relative_to(root).as_posix(),
        "remote_manifest_sha256": sealed["manifest_sha256"],
        "selected_feature_ids": selection_valid["selected_feature_ids"],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--artifact-receipt", type=Path, required=True)
    parser.add_argument("--calibration-receipt", type=Path, required=True)
    parser.add_argument("--selection-receipt", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run(
        cache_dir=args.cache_dir,
        artifact_receipt_path=args.artifact_receipt,
        calibration_receipt_path=args.calibration_receipt,
        selection_receipt_path=args.selection_receipt,
        artifact_root=args.artifact_root,
        volume_id=args.volume_id,
        run_id=args.run_id,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
