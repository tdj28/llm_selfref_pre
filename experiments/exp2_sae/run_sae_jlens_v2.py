#!/usr/bin/env python3
"""Execute the preregistered SAE/J-lens v2 residual and readout collection."""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterable

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
for search_path in (REPO_ROOT, SCRIPT_DIR):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from experiments.exp2_sae.run_sae_jlens_audit import (  # noqa: E402
    ReadoutEngine,
    build_lexicon as build_v1_lexicon,
    capture_trajectory,
    download_artifacts,
    exact_content_positions,
    extract_decoder_directions,
    load_lens,
    load_model,
    load_sae_state,
    position_batch,
    runtime_metadata,
    smoke_direct_addition,
    tensor_sha256,
    utc_now,
    vector_from_plan,
)
from experiments.exp2_sae.sae_jlens_protocol import (  # noqa: E402
    TRANSPORT_RANDOM_SEEDS,
)
from experiments.exp2_sae.sae_jlens_v2_final_protocol import (  # noqa: E402
    FINAL_PLAN_DIR,
)
from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    MODEL_WIDTH,
    POSITIONS,
    PROTOCOL_VERSION,
    REPLAY_ABS_TOLERANCE,
    RESIDUAL_SHARD_ROWS,
    TRAJECTORY_LAYERS,
    V1_RELEASE_DIR,
    read_jsonl,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / FINAL_PLAN_DIR
DEFAULT_OUTDIR = Path("/workspace/results/sae_jlens_v2_20260712")
DEFAULT_CACHE_DIR = Path("/workspace/hf-cache")
EXPECTED_REGISTRATION_TITLE = (
    "SAE-Jacobian Lens V2: Hard Negatives and Reader Capacity"
)
INDEX_FIELDS = [
    "trial_id",
    "execution_order",
    "shard",
    "row_offset",
    "prompt_id",
    "template_id",
    "category",
    "condition_family",
    "sign",
    "matched_target_feature_id",
    "semantic_experiment",
    "semantic_family",
    "comparator_feature_id",
    "prompt_fold",
    "source_v1_trial_id",
]


class ProtocolViolation(RuntimeError):
    """A fail-closed discrepancy from the frozen final plan."""


def public_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.api+json"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def public_sha256(url: str) -> str:
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=600) as response:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_public_registration(gate: dict[str, Any], plan_hash: str, head: str) -> None:
    if gate.get("public_anonymous_access_verified") is not True:
        raise ProtocolViolation("Registration gate lacks anonymous-access verification")
    if gate.get("registered_response_binding_verified") is not True:
        raise ProtocolViolation("Registration gate lacks response-binding verification")
    registration_id = str(gate["registration_id"])
    api_url = f"https://api.osf.io/v2/registrations/{registration_id}/"
    data = public_json(api_url)["data"]
    attributes = data.get("attributes", {})
    if data.get("id") != registration_id or data.get("type") != "registrations":
        raise ProtocolViolation("Public OSF registration identity differs")
    if (
        attributes.get("registration") is not True
        or attributes.get("public") is not True
        or attributes.get("withdrawn") is not False
        or attributes.get("pending_registration_approval") is not False
        or attributes.get("pending_embargo_approval") is not False
        or not attributes.get("date_registered")
        or attributes.get("title") != EXPECTED_REGISTRATION_TITLE
        or attributes.get("registration_supplement") != "Open-Ended Registration"
    ):
        raise ProtocolViolation("Public OSF registration state is not accepted")
    registered_meta = json.dumps(attributes.get("registered_meta", {}), sort_keys=True)
    if head not in registered_meta or plan_hash not in registered_meta:
        raise ProtocolViolation("Public OSF responses do not bind this checkout and plan")
    registered_from = json.dumps(
        data.get("relationships", {}).get("registered_from", {}), sort_keys=True
    )
    project_id = str(gate.get("project_id", ""))
    if not project_id or project_id not in registered_from:
        raise ProtocolViolation("Public OSF registration source project differs")
    files = gate.get("registered_snapshot_files", [])
    expected_names = {
        "OSF_REGISTRATION_SUMMARY.md",
        "SAE_JLENS_V2_PREREGISTRATION_PACKET.zip",
        "OSF_PACKET_MANIFEST.json",
    }
    if len(files) != 3 or {row.get("name") for row in files} != expected_names:
        raise ProtocolViolation("Registered OSF packet file set differs")
    for row in files:
        expected_hash = str(row.get("sha256", ""))
        download_url = str(row.get("download_url", ""))
        if (
            len(expected_hash) != 64
            or not download_url.startswith("https://")
            or row.get("anonymous_download_sha256") != expected_hash
            or public_sha256(download_url) != expected_hash
        ):
            raise ProtocolViolation(f"Registered OSF file differs: {row.get('name')}")


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()


def verify_plan_and_registration(
    plan_dir: Path, registration_gate_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path = plan_dir / "PLAN_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "final_result_free_plan":
        raise ProtocolViolation("Final plan status differs")
    for record in manifest.get("files", []):
        path = plan_dir / record["path"]
        if not path.is_file() or path.stat().st_size != int(record["bytes"]):
            raise ProtocolViolation(f"Final plan file differs: {path}")
        if sha256_file(path) != record["sha256"]:
            raise ProtocolViolation(f"Final plan hash differs: {path}")
    for record in manifest.get("source_files", []):
        path = REPO_ROOT / record["path"]
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ProtocolViolation(f"Final plan source differs: {path}")

    gate = json.loads(registration_gate_path.read_text(encoding="utf-8"))
    plan_hash = sha256_file(manifest_path)
    head = git_head()
    if gate.get("status") != "accepted_public_registration":
        raise ProtocolViolation("OSF registration gate is not accepted and public")
    if gate.get("plan_manifest_sha256") != plan_hash:
        raise ProtocolViolation("OSF registration binds a different plan manifest")
    if gate.get("freeze_commit") != head:
        raise ProtocolViolation("Runtime checkout differs from OSF-bound freeze commit")
    registration_url = str(gate.get("registration_url", ""))
    if not registration_url.startswith("https://osf.io/"):
        raise ProtocolViolation("OSF registration URL differs")
    if not gate.get("registration_id"):
        raise ProtocolViolation("OSF registration ID is absent")
    verify_public_registration(gate, plan_hash, head)
    return manifest, gate


def verify_gpu(torch_module: Any) -> None:
    if not torch_module.cuda.is_available() or torch_module.cuda.device_count() != 1:
        raise ProtocolViolation("Stage 1 requires exactly one CUDA GPU")
    memory = torch_module.cuda.get_device_properties(0).total_memory
    if memory < 170 * 1024**3:
        raise ProtocolViolation(
            f"Stage 1 requires at least 170 GiB VRAM, found {memory / 1024**3:.2f}"
        )


def verify_v1_release() -> None:
    release_dir = REPO_ROOT / V1_RELEASE_DIR
    manifest = json.loads(
        (release_dir / "RELEASE_MANIFEST.json").read_text(encoding="utf-8")
    )
    if manifest.get("status") != "complete_public_release":
        raise ProtocolViolation("Canonical v1 release is not complete")
    for record in manifest.get("files", []):
        relative = str(record["path"])
        if not (
            relative == "lexicon_tokens.json"
            or relative.startswith("paired_results/")
        ):
            continue
        path = release_dir / relative
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ProtocolViolation(f"Canonical v1 release hash differs: {path}")


def exact_v2_lexicon(tokenizer: Any, frozen: dict[str, Any]) -> dict[str, Any]:
    accepted = frozen.get("accepted", {})
    rejected = frozen.get("rejected", {})
    for family, rows in accepted.items():
        if len(rows) < 5:
            raise ProtocolViolation(f"V2 lexicon is too small: {family}")
        for row in rows:
            candidate = str(row["candidate"])
            token_ids = tokenizer(candidate, add_special_tokens=False)["input_ids"]
            decoded = tokenizer.decode(
                token_ids, clean_up_tokenization_spaces=False
            )
            if token_ids != [int(row["token_id"])] or decoded != candidate:
                raise ProtocolViolation(f"V2 lexicon token differs: {family}/{candidate}")
    observed_ids = [
        int(row["token_id"])
        for rows in accepted.values()
        for row in rows
    ]
    if len(observed_ids) != len(set(observed_ids)):
        raise ProtocolViolation("V2 lexicon token IDs overlap")
    return {"accepted": accepted, "rejected": rejected}


def combined_lexicon(
    tokenizer: Any, plan_dir: Path
) -> tuple[dict[str, Any], list[int]]:
    v1_observed = build_v1_lexicon(tokenizer)
    v1_frozen = json.loads(
        (REPO_ROOT / V1_RELEASE_DIR / "lexicon_tokens.json").read_text(
            encoding="utf-8"
        )
    )
    if v1_observed != v1_frozen:
        raise ProtocolViolation("Canonical v1 lexicon failed tokenizer replay")
    v2_frozen = json.loads(
        (plan_dir / "lexicon_tokens.json").read_text(encoding="utf-8")
    )
    v2_observed = exact_v2_lexicon(tokenizer, v2_frozen)
    accepted = {
        **{f"v1_{key}": value for key, value in v1_observed["accepted"].items()},
        **{f"v2_{key}": value for key, value in v2_observed["accepted"].items()},
    }
    rejected = {
        **{f"v1_{key}": value for key, value in v1_observed["rejected"].items()},
        **{f"v2_{key}": value for key, value in v2_observed["rejected"].items()},
    }
    v1_token_ids = sorted(
        {
            int(row["token_id"])
            for rows in v1_observed["accepted"].values()
            for row in rows
        }
    )
    if len(v1_token_ids) != 67:
        raise ProtocolViolation("Canonical v1 lexicon does not contain 67 tokens")
    return {"accepted": accepted, "rejected": rejected}, v1_token_ids


def feature_ids_for_plan(trials: Iterable[dict[str, Any]]) -> list[int]:
    values: set[int] = set()
    for row in trials:
        values.update(int(value) for value in row.get("feature_ids", []))
        values.update(int(value) for value in row.get("norm_source_feature_ids", []))
    return sorted(values)


def atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    os.replace(temporary, path)


def atomic_safetensors(path: Path, tensor: Any) -> None:
    from safetensors.torch import save_file

    temporary = path.with_suffix(path.suffix + ".tmp")
    save_file({"residuals": tensor.contiguous()}, str(temporary))
    os.replace(temporary, path)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def shard_paths(outdir: Path, shard: int) -> tuple[Path, Path, Path]:
    name = f"part-{shard:03d}"
    return (
        outdir / "residuals" / f"{name}.safetensors",
        outdir / "readouts" / f"{name}.jsonl",
        outdir / "residual_index_parts" / f"{name}.jsonl",
    )


def validate_completed_shard(
    paths: tuple[Path, Path, Path], planned: list[dict[str, Any]]
) -> bool:
    exists = [path.exists() for path in paths]
    if not any(exists):
        return False
    if not all(exists):
        raise ProtocolViolation(f"Incomplete immutable shard triple: {paths}")
    from safetensors import safe_open

    with safe_open(paths[0], framework="pt", device="cpu") as handle:
        residuals = handle.get_tensor("residuals")
        shape = tuple(residuals.shape)
    if shape != (len(planned), len(TRAJECTORY_LAYERS), len(POSITIONS), MODEL_WIDTH):
        raise ProtocolViolation(f"Completed residual shard shape differs: {paths[0]}")
    if str(residuals.dtype) != "torch.bfloat16":
        raise ProtocolViolation(f"Completed residual shard dtype differs: {paths[0]}")
    readouts = load_jsonl(paths[1])
    index = load_jsonl(paths[2])
    expected_ids = [row["trial_id"] for row in planned]
    if [row["trial_id"] for row in readouts] != expected_ids:
        raise ProtocolViolation(f"Completed readout shard IDs differ: {paths[1]}")
    if [row["trial_id"] for row in index] != expected_ids:
        raise ProtocolViolation(f"Completed index shard IDs differ: {paths[2]}")
    return True


def collect_shard(
    torch_module: Any,
    model: Any,
    tokenizer: Any,
    engine: ReadoutEngine,
    directions: dict[int, Any],
    planned: list[dict[str, Any]],
    shard: int,
    outdir: Path,
    v1_token_ids: list[int],
) -> None:
    residual_rows = []
    compact_rows: list[dict[str, Any]] = []
    index_rows: list[dict[str, Any]] = []
    token_cache: dict[str, tuple[Any, dict[str, Any]]] = {}
    transports = ["jacobian", "identity"] + [
        f"random_j_{index}" for index in range(1, len(TRANSPORT_RANDOM_SEEDS) + 1)
    ]
    v1_indices = [engine.token_index[token_id] for token_id in v1_token_ids]
    started = time.monotonic()

    for offset, plan_row in enumerate(planned):
        prompt_id = str(plan_row["prompt_id"])
        if prompt_id not in token_cache:
            token_cache[prompt_id] = exact_content_positions(
                tokenizer, str(plan_row["text"])
            )
        input_ids, position_metadata = token_cache[prompt_id]
        intervention = vector_from_plan(torch_module, plan_row, directions)
        if intervention is not None:
            if not bool(torch_module.isfinite(intervention).all()):
                raise ProtocolViolation(f"Nonfinite intervention: {plan_row['trial_id']}")
            if float(intervention.float().norm().item()) <= 0:
                raise ProtocolViolation(f"Zero nonzero intervention: {plan_row['trial_id']}")
        captures, diagnostics = capture_trajectory(
            torch_module, model, input_ids, intervention
        )
        layer_batches = []
        readouts: list[dict[str, Any]] = []
        for layer in TRAJECTORY_LAYERS:
            residual_batch, position_names = position_batch(
                captures[layer], position_metadata
            )
            layer_batches.append(residual_batch.detach().to("cpu", torch_module.bfloat16))
            for transport in transports:
                transported = engine.transport(residual_batch, layer, transport)
                logits = engine.selected_logits(transported)
                for position_index, position_name in enumerate(position_names):
                    group_logits, token_logits = engine.summarize_selected(
                        logits[position_index : position_index + 1]
                    )
                    readout = {
                        "layer": layer,
                        "position": position_name,
                        "transport": transport,
                        "source_norm": float(
                            residual_batch[position_index].float().norm().item()
                        ),
                        "transported_norm": float(
                            transported[position_index].float().norm().item()
                        ),
                        "group_logits": group_logits,
                    }
                    if plan_row.get("source_v1_trial_id") is not None:
                        readout["v1_token_logits"] = [
                            token_logits[index] for index in v1_indices
                        ]
                    readouts.append(readout)
                del transported, logits
            del residual_batch
        residual_rows.append(torch_module.stack(layer_batches))
        compact_rows.append(
            {
                **plan_row,
                "protocol_version": PROTOCOL_VERSION,
                "captured_at_utc": utc_now(),
                "position_metadata": position_metadata,
                "intervention": {
                    "vector_sha256_bfloat16": (
                        None if intervention is None else tensor_sha256(intervention)
                    ),
                    "vector_norm": (
                        0.0
                        if intervention is None
                        else float(intervention.float().norm().item())
                    ),
                    **diagnostics,
                },
                "readouts": readouts,
            }
        )
        index_rows.append(
            {
                key: (
                    f"part-{shard:03d}.safetensors"
                    if key == "shard"
                    else offset
                    if key == "row_offset"
                    else plan_row.get(key)
                )
                for key in INDEX_FIELDS
            }
        )
        del captures, intervention, layer_batches, readouts

    residual_tensor = torch_module.stack(residual_rows)
    expected_shape = (
        len(planned),
        len(TRAJECTORY_LAYERS),
        len(POSITIONS),
        MODEL_WIDTH,
    )
    if tuple(residual_tensor.shape) != expected_shape:
        raise ProtocolViolation(f"Residual shard shape differs: {residual_tensor.shape}")
    residual_path, readout_path, index_path = shard_paths(outdir, shard)
    atomic_safetensors(residual_path, residual_tensor)
    atomic_jsonl(readout_path, compact_rows)
    atomic_jsonl(index_path, index_rows)
    elapsed = time.monotonic() - started
    print(
        json.dumps(
            {
                "phase": "collection",
                "shard": shard,
                "rows": len(planned),
                "seconds": elapsed,
                "rows_per_second": len(planned) / elapsed if elapsed else None,
            },
            sort_keys=True,
        ),
        flush=True,
    )


def write_complete_index(outdir: Path) -> None:
    rows = []
    for path in sorted((outdir / "residual_index_parts").glob("part-*.jsonl")):
        rows.extend(load_jsonl(path))
    rows.sort(key=lambda row: int(row["execution_order"]))
    if len(rows) != 4_029 or len({row["trial_id"] for row in rows}) != len(rows):
        raise ProtocolViolation("Complete residual index is incomplete or duplicated")
    path = outdir / "residual_index.csv"
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def canonical_v1_rows() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    directory = REPO_ROOT / V1_RELEASE_DIR / "paired_results"
    for path in sorted(directory.glob("part-*.jsonl")):
        for row in load_jsonl(path):
            trial_id = str(row["trial_id"])
            if trial_id in rows:
                raise ProtocolViolation(f"Duplicate canonical v1 trial: {trial_id}")
            rows[trial_id] = row
    if len(rows) != 1_581:
        raise ProtocolViolation(f"Canonical v1 row count differs: {len(rows)}")
    return rows


def v1_reproduction_gate(outdir: Path) -> dict[str, Any]:
    canonical = canonical_v1_rows()
    differences: list[np.ndarray] = []
    compared = 0
    for path in sorted((outdir / "readouts").glob("part-*.jsonl")):
        for row in load_jsonl(path):
            source_id = row.get("source_v1_trial_id")
            if source_id is None:
                continue
            expected = canonical.pop(str(source_id), None)
            if expected is None:
                raise ProtocolViolation(f"Unknown or duplicate v1 source: {source_id}")
            observed_readouts = row["readouts"]
            expected_readouts = expected["readouts"]
            if len(observed_readouts) != len(expected_readouts):
                raise ProtocolViolation(f"V1 readout count differs: {source_id}")
            for observed, prior in zip(observed_readouts, expected_readouts):
                key = ("layer", "position", "transport")
                if tuple(observed[name] for name in key) != tuple(
                    prior[name] for name in key
                ):
                    raise ProtocolViolation(f"V1 readout identity differs: {source_id}")
                delta = np.abs(
                    np.asarray(observed["v1_token_logits"], dtype=np.float64)
                    - np.asarray(prior["token_logits"], dtype=np.float64)
                )
                differences.append(delta)
            compared += 1
    if canonical or compared != 1_581:
        raise ProtocolViolation("V1 reproduction gate did not cover all source rows")
    values = np.concatenate(differences)
    maximum = float(values.max())
    return {
        "status": "pass" if maximum <= REPLAY_ABS_TOLERANCE else "fail",
        "rows": compared,
        "values_compared": int(values.size),
        "maximum_absolute_error": maximum,
        "median_absolute_error": float(np.median(values)),
        "p99_absolute_error": float(np.quantile(values, 0.99)),
        "tolerance": REPLAY_ABS_TOLERANCE,
    }


def storage_fidelity_gate(
    torch_module: Any,
    engine: ReadoutEngine,
    outdir: Path,
    v1_token_ids: list[int],
) -> dict[str, Any]:
    from safetensors.torch import load_file

    transports = ["jacobian", "identity"] + [
        f"random_j_{index}" for index in range(1, len(TRANSPORT_RANDOM_SEEDS) + 1)
    ]
    v1_indices = [engine.token_index[token_id] for token_id in v1_token_ids]
    differences: list[np.ndarray] = []
    compared_rows = 0
    for shard_path in sorted((outdir / "residuals").glob("part-*.safetensors")):
        readout_path = outdir / "readouts" / f"{shard_path.stem}.jsonl"
        rows = load_jsonl(readout_path)
        replay_indices = [
            index
            for index, row in enumerate(rows)
            if row.get("source_v1_trial_id") is not None
        ]
        if not replay_indices:
            continue
        residuals = load_file(str(shard_path), device="cpu")["residuals"]
        selected = residuals[replay_indices].to("cuda")
        expected_by_row = [rows[index]["readouts"] for index in replay_indices]
        for layer_index, layer in enumerate(TRAJECTORY_LAYERS):
            batch = selected[:, layer_index].reshape(-1, MODEL_WIDTH)
            for transport_index, transport in enumerate(transports):
                transported = engine.transport(batch, layer, transport)
                logits = engine.selected_logits(transported)[:, v1_indices]
                observed = logits.float().cpu().numpy().reshape(
                    len(replay_indices), len(POSITIONS), len(v1_token_ids)
                )
                expected = np.asarray(
                    [
                        [
                            expected_by_row[row_index][
                                (layer_index * len(transports) + transport_index)
                                * len(POSITIONS)
                                + position_index
                            ]["v1_token_logits"]
                            for position_index in range(len(POSITIONS))
                        ]
                        for row_index in range(len(replay_indices))
                    ],
                    dtype=np.float32,
                )
                differences.append(np.abs(observed - expected).reshape(-1))
                del transported, logits
            del batch
        compared_rows += len(replay_indices)
        del residuals, selected
        torch_module.cuda.empty_cache()
    if compared_rows != 1_581:
        raise ProtocolViolation(f"Storage fidelity covered {compared_rows} replay rows")
    values = np.concatenate(differences)
    maximum = float(values.max())
    return {
        "status": "pass" if maximum <= REPLAY_ABS_TOLERANCE else "fail",
        "rows": compared_rows,
        "values_compared": int(values.size),
        "maximum_absolute_error": maximum,
        "median_absolute_error": float(np.median(values)),
        "p99_absolute_error": float(np.quantile(values, 0.99)),
        "tolerance": REPLAY_ABS_TOLERANCE,
    }


def result_inventory(outdir: Path) -> list[dict[str, Any]]:
    excluded = {"RESULT_MANIFEST.json", "RUN_COMPLETE.json"}
    return [
        {
            "path": path.relative_to(outdir).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(outdir.rglob("*"))
        if path.is_file()
        and path.name not in excluded
        and not path.name.endswith((".tmp", ".log"))
    ]


def completed_run_is_immutable(outdir: Path) -> bool:
    complete_path = outdir / "RUN_COMPLETE.json"
    manifest_path = outdir / "RESULT_MANIFEST.json"
    if not complete_path.exists() and not manifest_path.exists():
        return False
    if not complete_path.is_file() or not manifest_path.is_file():
        raise ProtocolViolation("Only one completed-run marker exists")
    complete = json.loads(complete_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if complete.get("status") != "complete" or manifest.get("status") != "complete":
        raise ProtocolViolation("Existing terminal run is not a passing immutable run")
    for record in manifest.get("files", []):
        path = outdir / record["path"]
        if not path.is_file() or path.stat().st_size != int(record["bytes"]):
            raise ProtocolViolation(f"Completed result file differs: {path}")
        if sha256_file(path) != record["sha256"]:
            raise ProtocolViolation(f"Completed result hash differs: {path}")
    print(
        json.dumps(
            {
                "status": "already_complete_verified_noop",
                "result_manifest_sha256": sha256_file(manifest_path),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return True


def run(args: argparse.Namespace) -> None:
    plan_dir = args.plan_dir.resolve()
    outdir = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    for directory in ("residuals", "readouts", "residual_index_parts"):
        (outdir / directory).mkdir(exist_ok=True)
    temporary_files = list(outdir.rglob("*.tmp"))
    if temporary_files and not args.resume:
        raise ProtocolViolation(f"Temporary files require --resume: {temporary_files}")
    for path in temporary_files:
        path.unlink()

    manifest, registration_gate = verify_plan_and_registration(
        plan_dir, args.registration_gate.resolve()
    )
    if completed_run_is_immutable(outdir):
        return
    verify_v1_release()
    import torch

    verify_gpu(torch)
    metadata = runtime_metadata(torch)
    metadata.update(
        {
            "freeze_commit": git_head(),
            "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
            "registration_id": registration_gate["registration_id"],
            "registration_url": registration_gate["registration_url"],
        }
    )
    write_json(outdir / "runtime_metadata.json", metadata)

    trials = read_jsonl(plan_dir / "trial_plan.jsonl")
    if len(trials) != 4_029:
        raise ProtocolViolation("Final trial count differs")
    sae_path, lens_path = download_artifacts(args.cache_dir.resolve())
    torch_module, model, tokenizer = load_model(args.cache_dir.resolve())
    combined, v1_token_ids = combined_lexicon(tokenizer, plan_dir)
    write_json(
        outdir / "lexicon_tokens.json",
        {"combined": combined, "v1_token_ids": v1_token_ids},
    )
    jacobians = load_lens(torch_module, lens_path)
    state, keys = load_sae_state(torch_module, sae_path)
    directions = extract_decoder_directions(
        torch_module, state, keys, feature_ids_for_plan(trials)
    )
    prompts = read_jsonl(REPO_ROOT / V1_RELEASE_DIR.parent / "confirmatory_v1_plan_20260711" / "prompt_plan.jsonl")
    smoke = smoke_direct_addition(
        torch_module, model, tokenizer, state, keys, directions, prompts[0]
    )
    write_json(outdir / "smoke_test.json", smoke)
    del state
    gc.collect()
    torch_module.cuda.empty_cache()
    engine = ReadoutEngine(torch_module, model, tokenizer, jacobians, combined)

    shard_count = math.ceil(len(trials) / RESIDUAL_SHARD_ROWS)
    for shard in range(shard_count):
        start = shard * RESIDUAL_SHARD_ROWS
        planned = trials[start : start + RESIDUAL_SHARD_ROWS]
        paths = shard_paths(outdir, shard)
        if validate_completed_shard(paths, planned):
            print(json.dumps({"phase": "resume", "shard": shard, "status": "verified"}))
            continue
        collect_shard(
            torch_module,
            model,
            tokenizer,
            engine,
            directions,
            planned,
            shard,
            outdir,
            v1_token_ids,
        )
    write_complete_index(outdir)

    storage_gate = storage_fidelity_gate(
        torch_module, engine, outdir, v1_token_ids
    )
    v1_gate = v1_reproduction_gate(outdir)
    gate = {
        "status": (
            "pass"
            if storage_gate["status"] == "pass" and v1_gate["status"] == "pass"
            else "fail"
        ),
        "storage_fidelity": storage_gate,
        "v1_reproduction": v1_gate,
    }
    write_json(outdir / "replay_equivalence_gate.json", gate)

    complete = gate["status"] == "pass"
    status = {
        "status": "complete" if complete else "replay_gate_failed",
        "completed_at_utc": utc_now(),
        "protocol_version": PROTOCOL_VERSION,
        "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
        "plan_manifest_status": manifest["status"],
        "freeze_commit": git_head(),
        "registration_id": registration_gate["registration_id"],
        "trial_rows": len(trials),
        "residual_shards": shard_count,
        "replay_gate_status": gate["status"],
    }
    write_json(outdir / "RUN_COMPLETE.json", status)
    write_json(outdir / "RESULT_MANIFEST.json", {**status, "files": result_inventory(outdir)})
    print(json.dumps(status, sort_keys=True), flush=True)
    if not complete:
        raise ProtocolViolation("Replay-equivalence gate failed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--registration-gate", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
