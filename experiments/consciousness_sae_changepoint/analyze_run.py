#!/usr/bin/env python3
"""Authorized, fail-closed entrypoint for confirmatory target analysis.

This module is intentionally separate from :mod:`analyze`, whose pure
functions are also used by target-blind power simulation.  The public
``run_authorized_analysis`` function performs no path resolution, manifest
read, plan read, or target-row read before
``seal.check_analysis_authorization`` returns successfully.

The authorized Stage-2A run must contain one self-hashed
``confirmatory_analysis_endpoint.json`` in the single passing attempt for each
prefix in the audit's common-complete set.  These rows contain the frozen
condition-blind automated labels and branch-level C3/C4 scores.  The current
executor does not yet produce that file, so analysis fails closed until the
model-facing endpoint builder is integrated before the target run is sealed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from experiments.consciousness_sae_changepoint import paths, seal
from experiments.consciousness_sae_changepoint.analyze import (
    AnalysisInputError,
    analyze_confirmatory_claims,
    c1_block_contrast,
    c2a_block_contrast,
    c2b_block_contrast,
    c3_block_contrast,
    c4_block_contrast,
    collapse_duplicate_clusters,
)
from experiments.consciousness_sae_changepoint.judge_prompts import (
    judge_prompt_receipt,
)
from experiments.consciousness_sae_changepoint.protocol import (
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
    MODEL_ID,
    MODEL_REVISION,
    PROTOCOL_VERSION,
    STUDY_ID,
    canonical_json_bytes,
)
from experiments.consciousness_sae_changepoint.storage import (
    BLOCK_MANIFEST,
    RunTransaction,
    sha256_file,
    validate_relative_path,
    verify_completed_block,
    verify_completed_run,
)
from experiments.consciousness_sae_changepoint.validate_plan import (
    validate as validate_plan,
)


ENDPOINT_SCHEMA_VERSION = 1
ANALYSIS_SCHEMA_VERSION = 1
ENDPOINT_FILENAME = "confirmatory_analysis_endpoint.json"
ANALYSIS_RECEIPT_FILENAME = "confirmatory_analysis_receipt.json"
BLOCK_CONTRASTS_FILENAME = "block_contrasts.json"
ANALYSIS_PHASE = "analysis"
MAX_ENDPOINT_BYTES = 8 * 1024**2
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PREFIX_ID = re.compile(r"^[0-9a-f]{24}$")
ATTEMPT_BLOCK = re.compile(r"^([0-9a-f]{24})-attempt-([01])$")
MECHANISM_BRANCHES = (
    "never",
    "target_supp",
    "target_amp",
    "matched_supp",
    "matched_amp",
)
BINARY_BRANCHES = (
    "target_supp",
    "target_amp",
    "matched_supp",
    "matched_amp",
)
ENDPOINT_FIELDS = {
    "schema_version",
    "study_id",
    "protocol_version",
    "plan_hash",
    "stage",
    "run_id",
    "prefix_id",
    "prefix_token_ids_sha256",
    "judge_definition_sha256",
    "endpoint_builder_source_sha256",
    "source_payload_sha256",
    "natural_stance_by_branch",
    "active_terminal_query_by_branch",
    "c3_report_polarity_j_scores_by_branch_layer",
    "c3_report_polarity_final_logits_by_branch",
    "c4_explicit_consciousness_j_scores_by_branch_layer",
    "c4_explicit_consciousness_final_logits_by_branch",
    "receipt_sha256",
}
SOURCE_PAYLOAD_FILES = (
    "main_branches.raw.json",
    "probes.raw.json",
    "actual_selected_readouts.json",
    "jlens_selected_readouts.json",
    "automated_judgments.json",
)
REQUIRED_ANALYSIS_SOURCE_PATHS = (
    "experiments/consciousness_sae_changepoint/analyze.py",
    "experiments/consciousness_sae_changepoint/analyze_run.py",
    "experiments/consciousness_sae_changepoint/seal.py",
)


class AuthorizedAnalysisError(RuntimeError):
    """Authorization, archive, endpoint, or analysis input failed closed."""


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _embedded_sha256(receipt: Mapping[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("receipt_sha256", None)
    return _sha256_json(payload)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def frozen_judge_definition_sha256() -> str:
    root = Path(__file__).resolve().parents[2]
    return _sha256_json(
        {
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "temperature": 0.0,
            "prompt_receipt": judge_prompt_receipt(),
            "judge_source_sha256": sha256_file(
                root / "experiments/consciousness_sae_changepoint/judge.py"
            ),
            "judge_prompts_source_sha256": sha256_file(
                root
                / "experiments/consciousness_sae_changepoint/judge_prompts.py"
            ),
        }
    )


def endpoint_builder_source_sha256() -> str:
    root = Path(__file__).resolve().parents[2]
    return sha256_file(root / "experiments/consciousness_sae_changepoint/run.py")


def _read_json(path: Path, *, label: str, maximum_bytes: int = MAX_ENDPOINT_BYTES) -> Any:
    if path.is_symlink() or not path.is_file():
        raise AuthorizedAnalysisError(f"{label} is not a regular non-symlink file")
    if path.stat().st_size <= 0 or path.stat().st_size > maximum_bytes:
        raise AuthorizedAnalysisError(f"{label} has an invalid byte count")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuthorizedAnalysisError(f"{label} is not valid JSON") from exc


def _exact_mapping(value: Any, fields: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise AuthorizedAnalysisError(f"{label} fields differ from the frozen schema")
    return value


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuthorizedAnalysisError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise AuthorizedAnalysisError(f"{label} must be finite")
    return number


def _branch_mapping(
    value: Any,
    branches: Sequence[str],
    *,
    label: str,
    binary: bool = False,
    stance: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(branches):
        raise AuthorizedAnalysisError(f"{label} branch set differs")
    result: dict[str, Any] = {}
    for branch in branches:
        raw = value[branch]
        if binary:
            if type(raw) is bool:
                result[branch] = raw
            elif type(raw) is int and raw in (0, 1):
                result[branch] = bool(raw)
            else:
                raise AuthorizedAnalysisError(f"{label} binary value differs")
        elif stance:
            if type(raw) is not int or raw not in {-1, 0, 1}:
                raise AuthorizedAnalysisError(f"{label} stance value differs")
            result[branch] = raw
        else:
            result[branch] = _finite(raw, label=f"{label} {branch}")
    return result


def _mechanism_layers(value: Any, *, label: str) -> dict[str, dict[int, float]]:
    if not isinstance(value, Mapping) or set(value) != set(MECHANISM_BRANCHES):
        raise AuthorizedAnalysisError(f"{label} branch set differs")
    expected = {str(layer) for layer in range(51, 79)}
    result: dict[str, dict[int, float]] = {}
    for branch in MECHANISM_BRANCHES:
        raw = value[branch]
        if not isinstance(raw, Mapping) or set(raw) != expected:
            raise AuthorizedAnalysisError(f"{label} layer grid differs for {branch}")
        result[branch] = {
            layer: _finite(raw[str(layer)], label=f"{label} {branch} layer {layer}")
            for layer in range(51, 79)
        }
    return result


def validate_endpoint_row(
    row: Mapping[str, Any],
    *,
    plan_hash: str,
    run_id: str,
    prefix_id: str,
    prefix_token_ids_sha256: str,
) -> dict[str, Any]:
    """Validate and normalize one authorized block-level endpoint row."""

    _exact_mapping(row, ENDPOINT_FIELDS, label="analysis endpoint row")
    if (
        row.get("schema_version") != ENDPOINT_SCHEMA_VERSION
        or row.get("study_id") != STUDY_ID
        or row.get("protocol_version") != PROTOCOL_VERSION
        or row.get("plan_hash") != plan_hash
        or row.get("stage") != "stage2a"
        or row.get("run_id") != run_id
        or row.get("prefix_id") != prefix_id
        or row.get("prefix_token_ids_sha256") != prefix_token_ids_sha256
        or row.get("judge_definition_sha256")
        != frozen_judge_definition_sha256()
        or row.get("endpoint_builder_source_sha256")
        != endpoint_builder_source_sha256()
    ):
        raise AuthorizedAnalysisError("analysis endpoint identity/binding differs")
    embedded = row.get("receipt_sha256")
    if not isinstance(embedded, str) or not HEX64.fullmatch(embedded):
        raise AuthorizedAnalysisError("analysis endpoint self-hash is missing")
    if _embedded_sha256(row) != embedded:
        raise AuthorizedAnalysisError("analysis endpoint self-hash differs")
    sources = row.get("source_payload_sha256")
    if (
        not isinstance(sources, Mapping)
        or set(sources) != set(SOURCE_PAYLOAD_FILES)
        or any(
            not isinstance(sources[name], str)
            or HEX64.fullmatch(sources[name]) is None
            for name in SOURCE_PAYLOAD_FILES
        )
    ):
        raise AuthorizedAnalysisError("analysis endpoint source-payload hashes differ")

    natural = _branch_mapping(
        row.get("natural_stance_by_branch"),
        MECHANISM_BRANCHES,
        label="natural stance",
        stance=True,
    )
    terminal = _branch_mapping(
        row.get("active_terminal_query_by_branch"),
        BINARY_BRANCHES,
        label="active terminal query",
        binary=True,
    )
    c3_j = _mechanism_layers(
        row.get("c3_report_polarity_j_scores_by_branch_layer"), label="C3 J"
    )
    c3_final = _branch_mapping(
        row.get("c3_report_polarity_final_logits_by_branch"),
        MECHANISM_BRANCHES,
        label="C3 final",
    )
    c4_j = _mechanism_layers(
        row.get("c4_explicit_consciousness_j_scores_by_branch_layer"),
        label="C4 J",
    )
    c4_final = _branch_mapping(
        row.get("c4_explicit_consciousness_final_logits_by_branch"),
        MECHANISM_BRANCHES,
        label="C4 final",
    )
    try:
        c3 = c3_block_contrast(c3_j, c3_final)
        c4 = c4_block_contrast(c4_j, c4_final)
        contrasts = {
            "C1": c1_block_contrast(natural),
            "C2a": c2a_block_contrast(terminal),
            "C2b": c2b_block_contrast(terminal),
            "C3_j": c3["post_depth_j_auc"],
            "C3_final": c3["actual_final_logit"],
            "C4_j": c4["post_depth_j_auc"],
            "C4_final": c4["actual_final_logit"],
        }
    except AnalysisInputError as exc:
        raise AuthorizedAnalysisError("endpoint contrast reconstruction failed") from exc
    return {
        "prefix_id": prefix_id,
        "prefix_token_ids_sha256": prefix_token_ids_sha256,
        "endpoint_receipt_sha256": embedded,
        **contrasts,
    }


def validate_endpoint_inventory(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_prefix_ids: Sequence[str],
    plan_hash: str,
    run_id: str,
    prefix_token_hashes: Mapping[str, str],
) -> list[dict[str, Any]]:
    expected = list(expected_prefix_ids)
    if (
        not expected
        or len(expected) != len(set(expected))
        or any(PREFIX_ID.fullmatch(value) is None for value in expected)
        or set(prefix_token_hashes) != set(expected)
    ):
        raise AuthorizedAnalysisError("authorized expected-prefix inventory is invalid")
    by_prefix: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise AuthorizedAnalysisError("analysis endpoint inventory contains a non-object")
        prefix_id = row.get("prefix_id")
        if not isinstance(prefix_id, str) or prefix_id in by_prefix:
            raise AuthorizedAnalysisError("analysis endpoint prefix ID is missing or duplicated")
        by_prefix[prefix_id] = row
    missing = sorted(set(expected) - set(by_prefix))
    unexpected = sorted(set(by_prefix) - set(expected))
    if missing or unexpected:
        raise AuthorizedAnalysisError(
            f"analysis endpoint row set differs; missing={missing}, unexpected={unexpected}"
        )
    return [
        validate_endpoint_row(
            by_prefix[prefix_id],
            plan_hash=plan_hash,
            run_id=run_id,
            prefix_id=prefix_id,
            prefix_token_ids_sha256=prefix_token_hashes[prefix_id],
        )
        for prefix_id in expected
    ]


def _resolved_beneath(root: Path, relative: str, *, label: str) -> Path:
    relative = validate_relative_path(relative)
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise AuthorizedAnalysisError(f"{label} path contains a symlink")
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise AuthorizedAnalysisError(f"{label} escapes the artifact root") from exc
    return resolved


def _passing_blocks(run_dir: Path, *, stage: str) -> dict[str, Path]:
    blocks_dir = run_dir / "blocks"
    if blocks_dir.is_symlink() or not blocks_dir.is_dir():
        raise AuthorizedAnalysisError("authorized target run has no regular blocks directory")
    by_prefix: dict[str, Path] = {}
    seen_attempts: dict[str, set[int]] = {}
    for block in sorted(path for path in blocks_dir.iterdir() if path.is_dir()):
        match = ATTEMPT_BLOCK.fullmatch(block.name)
        if match is None:
            raise AuthorizedAnalysisError("authorized target run has an invalid block ID")
        prefix_id, attempt_text = match.groups()
        attempt = int(attempt_text)
        if attempt in seen_attempts.setdefault(prefix_id, set()):
            raise AuthorizedAnalysisError("authorized target run duplicates an attempt")
        seen_attempts[prefix_id].add(attempt)
        verify_completed_block(block)
        manifest = _read_json(block / BLOCK_MANIFEST, label="target block manifest")
        metadata = manifest.get("metadata")
        if not isinstance(metadata, Mapping):
            raise AuthorizedAnalysisError("target block metadata is invalid")
        if metadata.get("status") == "pass":
            if metadata.get("stage") != stage or metadata.get("prefix_id") != prefix_id:
                raise AuthorizedAnalysisError("passing target block identity differs")
            if prefix_id in by_prefix:
                raise AuthorizedAnalysisError("a prefix has multiple passing attempts")
            by_prefix[prefix_id] = block
    return by_prefix


def _prefix_token_hashes(
    prefix_run: Path, expected_prefix_ids: Sequence[str]
) -> dict[str, str]:
    blocks = prefix_run / "blocks"
    if blocks.is_symlink() or not blocks.is_dir():
        raise AuthorizedAnalysisError("authorized prefix run has no blocks directory")
    result: dict[str, str] = {}
    for prefix_id in expected_prefix_ids:
        block = blocks / prefix_id
        if block.is_symlink() or not block.is_dir():
            raise AuthorizedAnalysisError(f"authorized prefix block is missing: {prefix_id}")
        verify_completed_block(block)
        compact = _read_json(
            block / "prefix_receipt.json", label="authorized compact prefix receipt"
        )
        digest = compact.get("prefix_token_ids_sha256") if isinstance(compact, Mapping) else None
        if (
            not isinstance(compact, Mapping)
            or compact.get("prefix_id") != prefix_id
            or compact.get("status") != "pass"
            or not isinstance(digest, str)
            or HEX64.fullmatch(digest) is None
        ):
            raise AuthorizedAnalysisError("authorized compact prefix binding differs")
        result[prefix_id] = digest
    return result


def _load_authorized_endpoint_rows(
    *,
    root: Path,
    audit: Mapping[str, Any],
    target_run_id: str,
) -> list[dict[str, Any]]:
    runs = audit.get("runs")
    common = audit.get("common_eligible")
    if not isinstance(runs, Mapping) or not isinstance(common, Mapping):
        raise AuthorizedAnalysisError("structural audit lacks run/common bindings")
    stage = runs.get("stage2a")
    prefix = runs.get("prefix_bank")
    if not isinstance(stage, Mapping) or not isinstance(prefix, Mapping):
        raise AuthorizedAnalysisError("structural audit target run bindings are missing")
    if stage.get("run_id") != target_run_id:
        raise AuthorizedAnalysisError("requested target run is not the authorized Stage-2A run")
    target_run = _resolved_beneath(root, str(stage.get("relative_path", "")), label="target run")
    prefix_run = _resolved_beneath(root, str(prefix.get("relative_path", "")), label="prefix run")
    for run_dir, binding, label in (
        (target_run, stage, "target"),
        (prefix_run, prefix, "prefix"),
    ):
        verification = verify_completed_run(run_dir)
        if verification.get("manifest_sha256") != binding.get("manifest_sha256"):
            raise AuthorizedAnalysisError(f"authorized {label} run manifest differs")
    expected = common.get("prefix_ids")
    if (
        not isinstance(expected, list)
        or expected != sorted(expected)
        or common.get("count") != len(expected)
        or common.get("prefix_ids_sha256") != _sha256_json(expected)
    ):
        raise AuthorizedAnalysisError("authorized common-prefix inventory differs")
    token_hashes = _prefix_token_hashes(prefix_run, expected)
    passing = _passing_blocks(target_run, stage="stage2a")
    missing_pass = sorted(set(expected) - set(passing))
    if missing_pass:
        raise AuthorizedAnalysisError(
            f"authorized common prefixes lack a passing target block: {missing_pass}"
        )
    rows: list[Mapping[str, Any]] = []
    for prefix_id in expected:
        block = passing[prefix_id]
        endpoint_path = block / ENDPOINT_FILENAME
        row = _read_json(endpoint_path, label=f"endpoint row {prefix_id}")
        if not isinstance(row, Mapping):
            raise AuthorizedAnalysisError("analysis endpoint file must contain one object")
        source_hashes = row.get("source_payload_sha256")
        if not isinstance(source_hashes, Mapping):
            raise AuthorizedAnalysisError("analysis endpoint source bindings are missing")
        for filename in SOURCE_PAYLOAD_FILES:
            source_path = block / filename
            if (
                source_path.is_symlink()
                or not source_path.is_file()
                or sha256_file(source_path) != source_hashes.get(filename)
            ):
                raise AuthorizedAnalysisError(
                    f"analysis endpoint source payload differs: {filename}"
                )
        rows.append(row)
    return validate_endpoint_inventory(
        rows,
        expected_prefix_ids=expected,
        plan_hash=str(audit["plan"]["plan_hash"]),
        run_id=target_run_id,
        prefix_token_hashes=token_hashes,
    )


def _collapse_inputs(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, list[float]], dict[str, list[float]], list[str]]:
    endpoints = ("C1", "C2a", "C2b", "C3_j", "C3_final", "C4_j", "C4_final")
    cluster_ids = [str(row["prefix_token_ids_sha256"]) for row in rows]
    collapsed: dict[str, list[float]] = {}
    weights: dict[str, list[float]] = {}
    common_cluster_ids: list[str] | None = None
    for endpoint in endpoints:
        values, endpoint_weights, ids = collapse_duplicate_clusters(
            [row[endpoint] for row in rows], cluster_ids
        )
        if common_cluster_ids is None:
            common_cluster_ids = ids
        elif ids != common_cluster_ids:
            raise AuthorizedAnalysisError("endpoint duplicate-cluster sets differ")
        collapsed[endpoint] = values
        weights[endpoint] = endpoint_weights
    return collapsed, weights, list(common_cluster_ids or [])


def _load_audit_after_authorization(
    *,
    structural_audit_receipt_path: Path,
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        audit, meta = seal._sealed_json(
            structural_audit_receipt_path,
            expected_filename=seal.STRUCTURAL_AUDIT_FILENAME,
            expected_phase="audit",
        )
        seal._validate_structural_audit_receipt(audit)
    except Exception as exc:
        raise AuthorizedAnalysisError("structural audit no longer validates") from exc
    if meta.get("artifact_root") != root:
        raise AuthorizedAnalysisError("structural audit belongs to another artifact root")
    return audit, meta


def _validate_plan_after_authorization(
    *, plan_dir: Path, volume_id: str, audit: Mapping[str, Any]
) -> dict[str, Any]:
    expanded = plan_dir.expanduser()
    if expanded.is_symlink():
        raise AuthorizedAnalysisError("frozen machine-plan directory may not be a symlink")
    try:
        resolved = expanded.resolve(strict=True)
        if not resolved.is_dir():
            raise AuthorizedAnalysisError("frozen machine plan is not a directory")
        validation = validate_plan(
            resolved,
            expected_volume_id=volume_id,
            repo_root=Path(__file__).resolve().parents[2],
        )
    except Exception as exc:
        raise AuthorizedAnalysisError("frozen machine plan no longer validates") from exc
    if (
        validation.get("status") != "pass"
        or validation.get("plan_hash") != audit["plan"]["plan_hash"]
        or sha256_file(resolved / "PLAN_MANIFEST.json")
        != audit["plan"]["plan_manifest_sha256"]
    ):
        raise AuthorizedAnalysisError("machine plan differs from the authorized audit")
    _require_analysis_sources_bound(resolved)
    return validation


def _require_analysis_sources_bound(plan_dir: Path) -> None:
    """Require the target-facing analysis chain in the prospective source seal.

    A hash written only into the result receipt describes post-hoc code; it
    does not prove that the analyzer was frozen.  This independent check blocks
    old plans until the exact build/validation source inventories include the
    authorization boundary and target-facing analyzer.
    """

    payload = _read_json(
        plan_dir / "source_files.json", label="frozen source-file receipt"
    )
    if not isinstance(payload, Mapping):
        raise AuthorizedAnalysisError("frozen source-file receipt is not an object")
    records = payload.get("files")
    if not isinstance(records, list):
        raise AuthorizedAnalysisError("frozen source-file inventory is missing")
    by_path: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise AuthorizedAnalysisError("frozen source-file record is not an object")
        relative = record.get("path")
        if not isinstance(relative, str) or relative in by_path:
            raise AuthorizedAnalysisError(
                "frozen source-file path is missing or duplicated"
            )
        by_path[relative] = record

    repo_root = Path(__file__).resolve().parents[2]
    for relative in REQUIRED_ANALYSIS_SOURCE_PATHS:
        record = by_path.get(relative)
        source = repo_root / relative
        if (
            record is None
            or set(record) != {"path", "bytes", "sha256", "outcome_bearing"}
            or record.get("outcome_bearing") is not False
            or source.is_symlink()
            or not source.is_file()
            or record.get("bytes") != source.stat().st_size
            or record.get("sha256") != sha256_file(source)
        ):
            raise AuthorizedAnalysisError(
                f"analysis source is absent or differs from the frozen plan: {relative}"
            )


def run_authorized_analysis(
    *,
    analysis_authorization_path: Path,
    unseal_receipt_path: Path,
    structural_audit_receipt_path: Path,
    human_reliability_receipt_path: Path,
    plan_dir: Path,
    artifact_root: Path,
    volume_id: str,
    target_run_id: str,
    analysis_run_id: str,
) -> dict[str, Any]:
    """Check the full unseal chain first, then read and analyze target rows."""

    # This must remain the first operation.  In particular, do not resolve an
    # outcome path or load an audit/plan before this call returns successfully.
    try:
        authorization = seal.check_analysis_authorization(
            analysis_authorization_path=analysis_authorization_path,
            unseal_receipt_path=unseal_receipt_path,
            structural_audit_receipt_path=structural_audit_receipt_path,
            human_reliability_receipt_path=human_reliability_receipt_path,
        )
    except Exception as exc:
        raise AuthorizedAnalysisError("analysis authorization check failed") from exc

    try:
        root = paths.require_external_artifact_root(
            artifact_root,
            minimum_free_bytes=seal.MIN_LIFECYCLE_FREE_BYTES,
            minimum_logical_reserve_bytes=seal.MIN_LIFECYCLE_FREE_BYTES,
            expected_volume_id=volume_id,
            write_read_probe=False,
        )
    except Exception as exc:
        raise AuthorizedAnalysisError("analysis artifact-root identity check failed") from exc
    audit, audit_meta = _load_audit_after_authorization(
        structural_audit_receipt_path=structural_audit_receipt_path,
        root=root,
    )
    if (
        authorization.get("status") != "authorized"
        or authorization.get("plan_hash") != audit["plan"]["plan_hash"]
        or authorization.get("common_eligible_prefixes")
        != audit["common_eligible"]["count"]
        or audit["plan"].get("volume_id") != volume_id
    ):
        raise AuthorizedAnalysisError("authorization plan/run/volume binding differs")
    _validate_plan_after_authorization(
        plan_dir=plan_dir, volume_id=volume_id, audit=audit
    )
    rows = _load_authorized_endpoint_rows(
        root=root, audit=audit, target_run_id=target_run_id
    )
    collapsed, weights, cluster_ids = _collapse_inputs(rows)
    try:
        analysis = analyze_confirmatory_claims(
            c1=collapsed["C1"],
            c2a_terminal=collapsed["C2a"],
            c2b_terminal=collapsed["C2b"],
            c3_j_auc=collapsed["C3_j"],
            c3_final_logit=collapsed["C3_final"],
            c4_j_auc=collapsed["C4_j"],
            c4_final_logit=collapsed["C4_final"],
            weights=weights,
            alpha=0.05,
            n_resamples=BOOTSTRAP_REPLICATES,
            seed=BOOTSTRAP_SEED,
        )
    except (AnalysisInputError, ValueError) as exc:
        raise AuthorizedAnalysisError("frozen confirmatory analysis failed") from exc

    block_rows = [
        {
            "prefix_id": row["prefix_id"],
            "prefix_token_ids_sha256": row["prefix_token_ids_sha256"],
            "endpoint_receipt_sha256": row["endpoint_receipt_sha256"],
            **{key: row[key] for key in ("C1", "C2a", "C2b", "C3_j", "C3_final", "C4_j", "C4_final")},
        }
        for row in rows
    ]
    transaction = RunTransaction.start(
        phase=ANALYSIS_PHASE,
        run_id=analysis_run_id,
        artifact_root=root,
        expected_volume_id=volume_id,
        minimum_free_bytes=seal.MIN_LIFECYCLE_FREE_BYTES,
        metadata={
            "study_id": STUDY_ID,
            "plan_hash": authorization["plan_hash"],
            "analysis_authorization_receipt_sha256": authorization["receipt_sha256"],
            "target_run_id": target_run_id,
        },
    )
    transaction.write_json(BLOCK_CONTRASTS_FILENAME, block_rows)
    receipt = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "receipt_kind": "confirmatory_analysis",
        "status": "complete",
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "created_at_utc": _utc_now(),
        "plan_hash": authorization["plan_hash"],
        "plan_manifest_sha256": audit["plan"]["plan_manifest_sha256"],
        "volume_id": volume_id,
        "analysis_authorization_receipt_sha256": authorization["receipt_sha256"],
        "analysis_authorization_manifest_sha256": authorization["manifest_sha256"],
        "structural_audit_manifest_sha256": audit_meta["manifest_sha256"],
        "target_run_id": target_run_id,
        "target_run_manifest_sha256": audit["runs"]["stage2a"]["manifest_sha256"],
        "common_prefix_count": len(rows),
        "common_prefix_ids_sha256": audit["common_eligible"]["prefix_ids_sha256"],
        "duplicate_cluster_count": len(cluster_ids),
        "duplicate_cluster_ids_sha256": _sha256_json(cluster_ids),
        "endpoint_receipt_inventory_sha256": _sha256_json(
            [row["endpoint_receipt_sha256"] for row in rows]
        ),
        "block_contrasts_sha256": _sha256_json(block_rows),
        "analysis_source_sha256": sha256_file(Path(__file__)),
        "analysis": analysis,
    }
    receipt["receipt_sha256"] = _embedded_sha256(receipt)
    transaction.write_json(ANALYSIS_RECEIPT_FILENAME, receipt)
    completed = transaction.complete(
        metadata={
            "status": "complete",
            "plan_hash": authorization["plan_hash"],
            "receipt_sha256": receipt["receipt_sha256"],
            "target_run_manifest_sha256": receipt["target_run_manifest_sha256"],
        }
    )
    verification = verify_completed_run(completed)
    return {
        "status": "complete",
        "analysis_run_id": analysis_run_id,
        "receipt_sha256": receipt["receipt_sha256"],
        "manifest_sha256": verification["manifest_sha256"],
        "common_prefix_count": len(rows),
        "duplicate_cluster_count": len(cluster_ids),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-authorization", type=Path, required=True)
    parser.add_argument("--unseal-receipt", type=Path, required=True)
    parser.add_argument("--structural-audit-receipt", type=Path, required=True)
    parser.add_argument("--human-reliability-receipt", type=Path, required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--target-run-id", required=True)
    parser.add_argument("--analysis-run-id", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        result = run_authorized_analysis(
            analysis_authorization_path=args.analysis_authorization,
            unseal_receipt_path=args.unseal_receipt,
            structural_audit_receipt_path=args.structural_audit_receipt,
            human_reliability_receipt_path=args.human_reliability_receipt,
            plan_dir=args.plan_dir,
            artifact_root=args.artifact_root,
            volume_id=args.volume_id,
            target_run_id=args.target_run_id,
            analysis_run_id=args.analysis_run_id,
        )
    except AuthorizedAnalysisError as exc:
        raise SystemExit(f"confirmatory analysis blocked: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
