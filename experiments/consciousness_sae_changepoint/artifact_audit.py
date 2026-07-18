#!/usr/bin/env python3
"""Receipt the pinned model, tokenizer, SAE, and every requested J map.

This command is target-blind: it loads public artifacts and frozen prompt
definitions, but it never runs a model forward or reads an experiment outcome.
The receipt is written only below the verified persistent artifact root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_changepoint.paths import (  # noqa: E402
    require_external_artifact_root,
)
from experiments.consciousness_sae_changepoint.storage import (  # noqa: E402
    RunTransaction,
    verify_completed_run,
)
from experiments.consciousness_sae_changepoint.protocol import (  # noqa: E402
    JLENS_FILENAME,
    JLENS_FILE_SHA256,
    JLENS_ID,
    JLENS_REVISION,
    J_MAP_LAYERS,
    LEXICON_CANDIDATES,
    MODEL_ID,
    MODEL_LAYERS,
    MODEL_REVISION,
    MODEL_WIDTH,
    SAE_FILENAME,
    SAE_FILE_SHA256,
    SAE_ID,
    SAE_REVISION,
    SAE_WIDTH,
    SELF_REFERENCE_PROMPT,
    STUDY_ID,
    TARGET_FEATURE_IDS,
    TOKENIZER_SIZE,
    canonical_json_bytes,
    sha256_file,
    sha256_text,
)
from src.prompts import BINARY_CONSCIOUS_QUERY  # noqa: E402


class ArtifactAuditError(RuntimeError):
    """Raised when a pinned artifact violates the frozen contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_key(state: dict[str, Any], suffix: str) -> str:
    matches = [key for key in state if key == suffix or key.endswith("." + suffix)]
    if len(matches) != 1:
        raise ArtifactAuditError(
            f"expected one SAE key ending in {suffix!r}, found {matches}"
        )
    return matches[0]


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _tensor_digest(tensor: Any) -> str:
    import torch

    contiguous = tensor.detach().to(device="cpu").contiguous()
    return hashlib.sha256(contiguous.view(torch.uint8).numpy()).hexdigest()


def _validate_lm_head_tensor(
    torch: Any,
    tensor: Any,
    *,
    expected_rows: int = TOKENIZER_SIZE,
    expected_width: int = MODEL_WIDTH,
) -> dict[str, Any]:
    """Validate the actual unembedding tensor, not only model configuration."""

    if tuple(tensor.shape) != (expected_rows, expected_width):
        raise ArtifactAuditError(
            "unexpected LM-head shape "
            f"{tuple(tensor.shape)}; expected {(expected_rows, expected_width)}"
        )
    if tensor.dtype != torch.bfloat16:
        raise ArtifactAuditError(f"unexpected LM-head dtype {tensor.dtype}")
    # Check in row chunks so finiteness validation does not allocate a second
    # full-vocabulary tensor on the host.
    for start in range(0, expected_rows, 4096):
        if not bool(torch.isfinite(tensor[start : start + 4096]).all()):
            raise ArtifactAuditError("LM-head tensor contains nonfinite values")
    return {
        "shape": list(tensor.shape),
        "dtype": str(tensor.dtype),
        "finite": True,
        "tensor_sha256": _tensor_digest(tensor),
    }


def _audit_lm_head(model_snapshot: Path, torch: Any) -> dict[str, Any]:
    """Locate and load the pinned LM head through its safetensors index."""

    from safetensors import safe_open

    index_path = model_snapshot / "model.safetensors.index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        shard_name = index["weight_map"]["lm_head.weight"]
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ArtifactAuditError("model index does not bind lm_head.weight") from exc
    if not isinstance(shard_name, str) or Path(shard_name).name != shard_name:
        raise ArtifactAuditError("LM-head shard name is not a snapshot-local filename")
    shard_path = model_snapshot / shard_name
    if not shard_path.is_file():
        raise ArtifactAuditError(f"LM-head shard is missing: {shard_name}")
    with safe_open(str(shard_path), framework="pt", device="cpu") as handle:
        if "lm_head.weight" not in handle.keys():
            raise ArtifactAuditError("indexed LM-head shard lacks lm_head.weight")
        tensor = handle.get_tensor("lm_head.weight")
    receipt = _validate_lm_head_tensor(torch, tensor)
    receipt.update(
        {
            "key": "lm_head.weight",
            "shard": shard_name,
            "shard_bytes": shard_path.stat().st_size,
            "shard_sha256": sha256_file(shard_path),
            "row_count_matches_tokenizer": int(tensor.shape[0]) == TOKENIZER_SIZE,
        }
    )
    del tensor
    return receipt


def _audit_tokenizer(snapshot: Path, token: str | None) -> tuple[Any, dict[str, Any]]:
    from transformers import AutoConfig, AutoTokenizer

    config = AutoConfig.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False, token=token
    )
    tokenizer = AutoTokenizer.from_pretrained(
        snapshot,
        local_files_only=True,
        trust_remote_code=False,
        token=token,
        use_fast=True,
    )
    text_config = config.get_text_config()
    if int(text_config.hidden_size) != MODEL_WIDTH:
        raise ArtifactAuditError(f"unexpected hidden width {text_config.hidden_size}")
    if int(text_config.num_hidden_layers) != MODEL_LAYERS:
        raise ArtifactAuditError(
            f"unexpected transformer depth {text_config.num_hidden_layers}"
        )
    if len(tokenizer) != TOKENIZER_SIZE:
        raise ArtifactAuditError(f"unexpected tokenizer length {len(tokenizer)}")
    token_ids = sorted(tokenizer.get_vocab().values())
    if token_ids != list(range(TOKENIZER_SIZE)):
        raise ArtifactAuditError("tokenizer IDs are not contiguous 0:128255")

    rendered = tokenizer.apply_chat_template(
        [{"role": "user", "content": SELF_REFERENCE_PROMPT}],
        add_generation_prompt=True,
        tokenize=False,
    )
    rendered_ids = tokenizer.apply_chat_template(
        [{"role": "user", "content": SELF_REFERENCE_PROMPT}],
        add_generation_prompt=True,
        tokenize=True,
    )
    query_messages = [
        {"role": "user", "content": SELF_REFERENCE_PROMPT},
        {"role": "assistant", "content": "Target-blind tokenizer fixture."},
        {"role": "user", "content": BINARY_CONSCIOUS_QUERY},
    ]
    query_probe = tokenizer.apply_chat_template(
        query_messages,
        add_generation_prompt=True,
        tokenize=True,
    )
    query_probe_text = tokenizer.apply_chat_template(
        query_messages,
        add_generation_prompt=True,
        tokenize=False,
    )
    contextual_answer_suffixes: dict[str, list[int]] = {}
    for answer in ("Yes", "No"):
        with_answer = tokenizer.encode(
            query_probe_text + answer, add_special_tokens=False
        )
        if with_answer[: len(query_probe)] != query_probe:
            raise ArtifactAuditError(
                f"query prefix is not token-prefix-stable when appending {answer!r}"
            )
        contextual_answer_suffixes[answer] = [
            int(value) for value in with_answer[len(query_probe) :]
        ]
    yes_ids = tokenizer.encode(" Yes", add_special_tokens=False)
    no_ids = tokenizer.encode(" No", add_special_tokens=False)
    return tokenizer, {
        "len": len(tokenizer),
        "base_vocab_size": int(tokenizer.vocab_size),
        "added_tokens": len(tokenizer) - int(tokenizer.vocab_size),
        "contiguous_id_sha256": sha256_text(
            ",".join(str(value) for value in token_ids)
        ),
        "chat_template_sha256": sha256_text(str(tokenizer.chat_template)),
        "rendered_induction_sha256": sha256_text(rendered),
        "rendered_induction_token_ids_sha256": sha256_text(
            ",".join(str(value) for value in rendered_ids)
        ),
        "rendered_induction_tokens": len(rendered_ids),
        "target_blind_query_fixture_token_ids_sha256": sha256_text(
            ",".join(str(value) for value in query_probe)
        ),
        "target_blind_query_fixture_tokens": len(query_probe),
        "isolated_yes_token_ids": yes_ids,
        "isolated_no_token_ids": no_ids,
        "isolated_yes_no_are_single_tokens": len(yes_ids) == len(no_ids) == 1,
        "contextual_answer_suffix_token_ids": contextual_answer_suffixes,
        "contextual_yes_no_are_single_tokens": all(
            len(values) == 1 for values in contextual_answer_suffixes.values()
        ),
        "lexicons": _audit_lexicons(tokenizer),
        "config_hidden_size": int(text_config.hidden_size),
        "config_num_hidden_layers": int(text_config.num_hidden_layers),
        "config_vocab_size": int(text_config.vocab_size),
    }


def _audit_lexicons(tokenizer: Any) -> dict[str, Any]:
    accepted: dict[str, list[dict[str, Any]]] = {}
    rejected: dict[str, list[dict[str, Any]]] = {}
    for group, candidates in LEXICON_CANDIDATES.items():
        accepted[group] = []
        rejected[group] = []
        for candidate in candidates:
            token_ids = [
                int(value)
                for value in tokenizer.encode(candidate, add_special_tokens=False)
            ]
            decoded = tokenizer.decode(
                token_ids, clean_up_tokenization_spaces=False
            )
            row = {
                "candidate": candidate,
                "token_ids": token_ids,
                "decoded": decoded,
            }
            if len(token_ids) == 1 and decoded == candidate:
                accepted[group].append({**row, "token_id": token_ids[0]})
            else:
                rejected[group].append(row)
        if len(accepted[group]) < 3:
            raise ArtifactAuditError(
                f"lexicon group {group!r} has only {len(accepted[group])} exact tokens"
            )
    return {
        "candidate_contract": "exact one-token encoding and decoded round trip",
        "accepted": accepted,
        "rejected": rejected,
    }


def audit(cache_dir: Path, *, expected_volume_id: str) -> dict[str, Any]:
    import torch
    from huggingface_hub import hf_hub_download, snapshot_download

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise ArtifactAuditError("artifact audit requires exactly one CUDA GPU")
    properties = torch.cuda.get_device_properties(0)
    if properties.total_memory < 170 * 1024**3:
        raise ArtifactAuditError(
            f"GPU has only {properties.total_memory} bytes; at least 170 GiB required"
        )

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    model_snapshot = Path(
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
    if sha256_file(sae_path) != SAE_FILE_SHA256:
        raise ArtifactAuditError("SAE file SHA-256 differs from the frozen value")
    if sha256_file(lens_path) != JLENS_FILE_SHA256:
        raise ArtifactAuditError("Jacobian-lens file SHA-256 differs from frozen value")

    _tokenizer, tokenizer_receipt = _audit_tokenizer(model_snapshot, token)
    # Hugging Face snapshots normally expose logical files as symlinks into the
    # content-addressed blob cache. Hash through those symlinks while recording
    # the stable snapshot-relative logical names.
    model_files = sorted(path for path in model_snapshot.rglob("*") if path.is_file())
    model_records = [_file_record(path, model_snapshot) for path in model_files]
    lm_head_receipt = _audit_lm_head(model_snapshot, torch)

    sae_state = torch.load(
        sae_path, map_location="cpu", weights_only=True, mmap=True
    )
    decoder_key = _state_key(sae_state, "decoder_linear.weight")
    encoder_key = _state_key(sae_state, "encoder_linear.weight")
    decoder = sae_state[decoder_key]
    encoder = sae_state[encoder_key]
    if tuple(decoder.shape) != (MODEL_WIDTH, SAE_WIDTH):
        raise ArtifactAuditError(f"unexpected SAE decoder shape {tuple(decoder.shape)}")
    if tuple(encoder.shape) != (SAE_WIDTH, MODEL_WIDTH):
        raise ArtifactAuditError(f"unexpected SAE encoder shape {tuple(encoder.shape)}")
    selected = decoder[:, list(TARGET_FEATURE_IDS)].float()
    if not bool(torch.isfinite(selected).all()):
        raise ArtifactAuditError("target SAE decoder columns contain nonfinite values")
    sae_receipt = {
        "file_bytes": sae_path.stat().st_size,
        "file_sha256": SAE_FILE_SHA256,
        "state_keys": sorted(sae_state),
        "decoder_key": decoder_key,
        "decoder_shape": list(decoder.shape),
        "decoder_dtype": str(decoder.dtype),
        "encoder_key": encoder_key,
        "encoder_shape": list(encoder.shape),
        "encoder_dtype": str(encoder.dtype),
        "target_columns_sha256": _tensor_digest(selected.to(dtype=torch.float32)),
        "target_decoder_norms": [
            float(value) for value in selected.square().sum(dim=0).sqrt().tolist()
        ],
    }
    del sae_state, decoder, encoder, selected

    checkpoint = torch.load(
        lens_path, map_location="cpu", weights_only=True, mmap=True
    )
    if not {"J", "n_prompts", "d_model"} <= set(checkpoint):
        raise ArtifactAuditError(f"unexpected lens keys {sorted(checkpoint)}")
    if int(checkpoint["d_model"]) != MODEL_WIDTH:
        raise ArtifactAuditError(f"unexpected lens width {checkpoint['d_model']}")
    available_layers = sorted(int(layer) for layer in checkpoint["J"])
    missing = sorted(set(J_MAP_LAYERS) - set(available_layers))
    if missing:
        raise ArtifactAuditError(f"lens is missing requested layers {missing}")

    generator = torch.Generator(device="cpu")
    generator.manual_seed(2_026_071_399)
    known = torch.randn(MODEL_WIDTH, generator=generator, dtype=torch.float32)
    layer_records: list[dict[str, Any]] = []
    for layer in J_MAP_LAYERS:
        cpu_matrix = checkpoint["J"][layer]
        if tuple(cpu_matrix.shape) != (MODEL_WIDTH, MODEL_WIDTH):
            raise ArtifactAuditError(
                f"unexpected J_{layer} shape {tuple(cpu_matrix.shape)}"
            )
        matrix = cpu_matrix.to(device="cuda", dtype=torch.float16).contiguous()
        if not bool(torch.isfinite(matrix).all()):
            raise ArtifactAuditError(f"J_{layer} contains nonfinite values")
        transported = known.to(device="cuda", dtype=torch.float16) @ matrix.T
        if not bool(torch.isfinite(transported).all()):
            raise ArtifactAuditError(f"known-vector J_{layer} result is nonfinite")
        layer_records.append(
            {
                "layer": layer,
                "shape": list(matrix.shape),
                "source_dtype": str(cpu_matrix.dtype),
                "runtime_dtype": str(matrix.dtype),
                "orientation": "residual @ J_L.T",
                "known_vector_output_sha256": _tensor_digest(transported),
                "known_vector_output_l2": float(
                    transported.float().square().sum().sqrt().item()
                ),
            }
        )
        del matrix, transported
    lens_receipt = {
        "file_bytes": lens_path.stat().st_size,
        "file_sha256": JLENS_FILE_SHA256,
        "checkpoint_keys": sorted(checkpoint),
        "n_prompts": int(checkpoint["n_prompts"]),
        "d_model": int(checkpoint["d_model"]),
        "available_layers": available_layers,
        "required_layers": list(J_MAP_LAYERS),
        "layer_records": layer_records,
    }
    del checkpoint
    torch.cuda.empty_cache()

    receipt = {
        "schema_version": 1,
        "status": "pass",
        "study_id": STUDY_ID,
        "outcome_blind": True,
        "prior_outcome_inputs": [],
        "created_at_utc": utc_now(),
        "expected_volume_id": expected_volume_id,
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": properties.name,
            "gpu_total_memory_bytes": int(properties.total_memory),
        },
        "model": {
            "id": MODEL_ID,
            "revision": MODEL_REVISION,
            "snapshot_file_count": len(model_records),
            "snapshot_total_bytes": sum(row["bytes"] for row in model_records),
            "files": model_records,
            "lm_head": lm_head_receipt,
        },
        "tokenizer": tokenizer_receipt,
        "sae": sae_receipt,
        "jacobian_lens": lens_receipt,
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical_json_bytes(receipt)).hexdigest()
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--volume-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = require_external_artifact_root(
        args.artifact_root,
        expected_volume_id=args.volume_id,
        write_read_probe=True,
    )
    transaction = RunTransaction.start(
        phase="benchmark",
        run_id=args.run_id,
        artifact_root=root,
        expected_volume_id=args.volume_id,
        metadata={
            "study_id": STUDY_ID,
            "outcome_blind": True,
            "prior_outcome_inputs": [],
            "role": "pinned_public_artifact_audit",
        },
    )
    receipt = audit(args.cache_dir.resolve(), expected_volume_id=args.volume_id)
    transaction.write_json("artifact_receipt.json", receipt)
    completed = transaction.complete(
        metadata={
            "study_id": STUDY_ID,
            "artifact_receipt_sha256": receipt["receipt_sha256"],
            "outcome_blind": True,
        }
    )
    sealed = verify_completed_run(completed)
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "completed_directory": str(completed.relative_to(root)),
                "receipt_sha256": receipt["receipt_sha256"],
                "remote_manifest_sha256": sealed["manifest_sha256"],
                "model_bytes": receipt["model"]["snapshot_total_bytes"],
                "lens_layers": len(receipt["jacobian_lens"]["layer_records"]),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
