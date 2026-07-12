#!/usr/bin/env python3
"""Audit the failed v2 run and its labeled post-outcome exploratory analysis."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae import audit_sae_jlens_v2_results as frozen_audit
from experiments.exp2_sae.sae_jlens_v2_final_protocol import FINAL_PLAN_DIR
from experiments.exp2_sae.sae_jlens_v2_protocol import (
    V1_RELEASE_DIR,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / FINAL_PLAN_DIR
DEFAULT_V1_DIR = REPO_ROOT / V1_RELEASE_DIR
THRESHOLDS = (0.0, 0.001, 0.002, 0.005, 0.01, 0.02, 0.03125, 0.05, 0.10, 0.20)
QUANTILES = (0.0, 0.5, 0.9, 0.95, 0.99, 0.999, 0.9999, 1.0)


class AuditFailure(RuntimeError):
    """The failed raw run, exploratory outputs, or their provenance differs."""


def jsonl_rows(paths: Iterable[Path]):
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def verify_remote_checksums(run_dir: Path, checksum_path: Path) -> dict[str, Any]:
    errors = []
    records = []
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split(maxsplit=1)
        relative = relative.removeprefix("./")
        path = run_dir / relative
        observed = sha256_file(path) if path.is_file() else None
        records.append({"path": relative, "sha256": digest, "matches": observed == digest})
        if observed != digest:
            errors.append(relative)
    if len(records) != 58:
        errors.append(f"expected 58 checksum records, found {len(records)}")
    return {
        "status": "pass" if not errors else "fail",
        "records": len(records),
        "checksum_file_sha256": sha256_file(checksum_path),
        "errors": errors,
    }


def verify_failed_raw(plan_dir: Path, run_dir: Path) -> dict[str, Any]:
    run = json.loads((run_dir / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
    gate = json.loads(
        (run_dir / "replay_equivalence_gate.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (run_dir / "RESULT_MANIFEST.json").read_text(encoding="utf-8")
    )
    errors = []
    if run.get("status") != "replay_gate_failed":
        errors.append("run status is not replay_gate_failed")
    if gate.get("status") != "fail":
        errors.append("replay gate is not failed")
    if gate.get("storage_fidelity", {}).get("status") != "pass":
        errors.append("storage fidelity did not pass")
    if gate.get("v1_reproduction", {}).get("status") != "fail":
        errors.append("v1 reproduction is not failed")
    if run.get("plan_manifest_sha256") != sha256_file(plan_dir / "PLAN_MANIFEST.json"):
        errors.append("plan binding differs")
    for record in manifest.get("files", []):
        path = run_dir / record["path"]
        if (
            not path.is_file()
            or path.stat().st_size != int(record["bytes"])
            or sha256_file(path) != record["sha256"]
        ):
            errors.append(f"result-manifest mismatch: {record['path']}")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "run": run,
        "gate": gate,
        "result_manifest_sha256": sha256_file(run_dir / "RESULT_MANIFEST.json"),
    }


def independent_replay(v1_dir: Path, run_dir: Path, diagnostic_path: Path) -> dict[str, Any]:
    canonical = {
        str(row["trial_id"]): row
        for row in jsonl_rows(sorted((v1_dir / "paired_results").glob("part-*.jsonl")))
    }
    if len(canonical) != 1_581:
        raise AuditFailure("Independent canonical v1 count differs")
    chunks = []
    signed_sum = squared_sum = 0.0
    count = rows = 0
    seen = set()
    stratum: dict[tuple[str, str], list[np.ndarray]] = defaultdict(list)
    for row in jsonl_rows(sorted((run_dir / "readouts").glob("part-*.jsonl"))):
        source_id = row.get("source_v1_trial_id")
        if source_id is None:
            continue
        source_id = str(source_id)
        if source_id in seen or source_id not in canonical:
            raise AuditFailure(f"Independent replay identity differs: {source_id}")
        seen.add(source_id)
        prior = canonical[source_id]
        for observed, expected in zip(row["readouts"], prior["readouts"]):
            identity = ("layer", "position", "transport")
            if tuple(observed[key] for key in identity) != tuple(
                expected[key] for key in identity
            ):
                raise AuditFailure(f"Independent readout identity differs: {source_id}")
            signed = np.asarray(observed["v1_token_logits"], dtype=np.float64) - np.asarray(
                expected["token_logits"], dtype=np.float64
            )
            absolute = np.abs(signed)
            chunks.append(absolute.astype(np.float32))
            signed_sum += float(signed.sum())
            squared_sum += float(np.square(signed).sum())
            count += signed.size
            for name, value in (
                ("layer", observed["layer"]),
                ("position", observed["position"]),
                ("transport", observed["transport"]),
            ):
                stratum[(name, str(value))].append(absolute)
        rows += 1
    if rows != 1_581 or seen != set(canonical) or count != 15_571_269:
        raise AuditFailure("Independent replay coverage differs")
    values = np.concatenate(chunks)
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    reported = diagnostic["overall"]
    observed = {
        "count": count,
        "mean_signed_error": signed_sum / count,
        "mean_absolute_error": float(values.mean(dtype=np.float64)),
        "rmse": math.sqrt(squared_sum / count),
        "maximum_absolute_error": float(values.max()),
        "absolute_error_quantiles": {
            str(level): float(value)
            for level, value in zip(QUANTILES, np.quantile(values, QUANTILES))
        },
        "thresholds": [
            {
                "threshold": threshold,
                "count_above": int(np.count_nonzero(values > threshold)),
                "proportion_above": float(np.count_nonzero(values > threshold) / count),
            }
            for threshold in THRESHOLDS
        ],
    }
    errors = []
    for field in ("count", "mean_signed_error", "mean_absolute_error", "rmse", "maximum_absolute_error"):
        if not math.isclose(float(observed[field]), float(reported[field]), abs_tol=1e-12):
            errors.append(f"overall {field} differs")
    for key, value in observed["absolute_error_quantiles"].items():
        if not math.isclose(value, float(reported["absolute_error_quantiles"][key]), abs_tol=1e-12):
            errors.append(f"quantile {key} differs")
    if observed["thresholds"] != reported["thresholds"]:
        errors.append("threshold table differs")
    reported_strata = {
        (name, str(row[name])): row
        for name, table in (
            ("layer", diagnostic["by_layer"]),
            ("position", diagnostic["by_position"]),
            ("transport", diagnostic["by_transport"]),
        )
        for row in table
    }
    for key, arrays in stratum.items():
        values_for_key = np.concatenate(arrays)
        expected = reported_strata.get(key)
        if expected is None:
            errors.append(f"missing diagnostic stratum: {key}")
            continue
        if (
            int(expected["count"]) != values_for_key.size
            or int(expected["above_0_02"]) != int(np.count_nonzero(values_for_key > 0.02))
            or not math.isclose(
                float(expected["maximum_absolute_error"]),
                float(values_for_key.max()),
                abs_tol=1e-12,
            )
        ):
            errors.append(f"diagnostic stratum differs: {key}")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "coverage": {"rows": rows, "values": count},
        "reconstructed_overall": observed,
        "diagnostic_sha256": sha256_file(diagnostic_path),
    }


def endpoint_overlay_audit(plan_dir: Path, run_dir: Path, analysis_dir: Path,
                           figures_dir: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="sae-jlens-v2-audit-") as temporary:
        overlay = Path(temporary)
        for path in run_dir.iterdir():
            if path.name in {"RUN_COMPLETE.json", "RESULT_MANIFEST.json", "replay_equivalence_gate.json", "post_failure"}:
                continue
            os.symlink(path.resolve(), overlay / path.name, target_is_directory=path.is_dir())
        run = json.loads((run_dir / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
        run["status"] = "complete"
        write_json(overlay / "RUN_COMPLETE.json", run)
        gate = json.loads(
            (run_dir / "replay_equivalence_gate.json").read_text(encoding="utf-8")
        )
        gate["status"] = "pass"
        write_json(overlay / "replay_equivalence_gate.json", gate)
        manifest = json.loads(
            (run_dir / "RESULT_MANIFEST.json").read_text(encoding="utf-8")
        )
        manifest["status"] = "complete"
        for record in manifest["files"]:
            if record["path"] == "replay_equivalence_gate.json":
                record["bytes"] = (overlay / record["path"]).stat().st_size
                record["sha256"] = sha256_file(overlay / record["path"])
        write_json(overlay / "RESULT_MANIFEST.json", manifest)
        overlay_analysis = overlay / "analysis"
        overlay_analysis.mkdir()
        for path in analysis_dir.iterdir():
            if path.name == "analysis_summary.json":
                continue
            os.symlink(path.resolve(), overlay_analysis / path.name)
        summary = json.loads(
            (analysis_dir / "analysis_summary.json").read_text(encoding="utf-8")
        )
        summary["status"] = "complete"
        write_json(overlay_analysis / "analysis_summary.json", summary)
        os.symlink(figures_dir.resolve(), overlay / "figures", target_is_directory=True)
        result = frozen_audit.audit(plan_dir, overlay)
    return {
        "status": result["status"],
        "frozen_independent_reconstruction": result,
        "overlay_disclosure": {
            "purpose": "Reuse the frozen independent endpoint reconstruction without mislabeling the released failed run.",
            "temporary_only": True,
            "changed_fields": [
                "RUN_COMPLETE.status: replay_gate_failed -> complete",
                "replay_equivalence_gate.status: fail -> pass",
                "RESULT_MANIFEST.status: replay_gate_failed -> complete",
                "analysis_summary.status: post_outcome_exploratory_complete -> complete",
            ],
            "scientific_values_changed": False,
        },
    }


def audit(plan_dir: Path, v1_dir: Path, run_dir: Path, checksum_path: Path,
          diagnostic: Path, analysis_dir: Path, figures_dir: Path) -> dict[str, Any]:
    raw = verify_failed_raw(plan_dir, run_dir)
    remote = verify_remote_checksums(run_dir, checksum_path)
    replay = independent_replay(v1_dir, run_dir, diagnostic)
    endpoints = endpoint_overlay_audit(plan_dir, run_dir, analysis_dir, figures_dir)
    summary = json.loads((analysis_dir / "analysis_summary.json").read_text(encoding="utf-8"))
    provenance = json.loads(
        (analysis_dir / "POST_FAILURE_ANALYSIS_PROVENANCE.json").read_text(encoding="utf-8")
    )
    labels_pass = (
        summary.get("analysis_class") == "post_outcome_exploratory"
        and summary.get("confirmatory_status") == "blocked_by_replay_gate"
        and provenance.get("implementation_correction", {}).get(
            "attempt_1_csv_hashes_identical"
        ) is True
    )
    components = {
        "failed_raw": raw["status"],
        "remote_retrieval": remote["status"],
        "independent_replay": replay["status"],
        "independent_endpoints": endpoints["status"],
        "post_outcome_labels": "pass" if labels_pass else "fail",
    }
    status = (
        "pass_post_outcome_exploratory_audit"
        if all(value == "pass" for value in components.values())
        else "fail"
    )
    return {
        "status": status,
        "confirmatory_status": "blocked_by_replay_gate",
        "components": components,
        "failed_raw": raw,
        "remote_retrieval": remote,
        "independent_replay": replay,
        "independent_endpoint_reconstruction": endpoints,
        "analysis_summary_sha256": sha256_file(analysis_dir / "analysis_summary.json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--v1-dir", type=Path, default=DEFAULT_V1_DIR)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--remote-checksums", type=Path, required=True)
    parser.add_argument("--diagnostic", type=Path, required=True)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--figures-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(
        args.plan_dir.resolve(), args.v1_dir.resolve(), args.run_dir.resolve(),
        args.remote_checksums.resolve(), args.diagnostic.resolve(),
        args.analysis_dir.resolve(), args.figures_dir.resolve(),
    )
    write_json(args.out.resolve(), result)
    print(json.dumps({"status": result["status"], "components": result["components"]}, sort_keys=True))
    if result["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
