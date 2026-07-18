#!/usr/bin/env python3
"""Build a compact, fail-closed adjudication for the one allowed Pro review."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import protocol


READY_LINE = re.compile(r"^(?:\*\*)?READY TO FREEZE(?:\*\*)?[.!]?$", re.I)
NEGATIVE_LINE = re.compile(
    r"^(?:\*\*)?(?:NOT READY TO FREEZE|READY AFTER SPECIFIED FIXES)\b",
    re.I,
)
REVIEW_PACKET = (
    (
        "docs/consciousness_sae_signed_dose_scan/PRO_REVIEW_BRIEF.md",
        "compact research-director plan brief",
    ),
    (
        "docs/consciousness_sae_signed_dose_scan/PRIOR_REVIEW_CONTEXT.md",
        "synthesized context 1",
    ),
    (
        "docs/consciousness_sae_signed_dose_scan/PRO_REVIEW_REPAIR_CONTEXT.md",
        "synthesized context 2",
    ),
)
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
EXPECTED_REVIEW_SCOPE = "director_level_plan_review"


class ReviewAdjudicationError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewAdjudicationError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ReviewAdjudicationError(f"JSON root is not an object: {path}")
    return value


def terminal_verdict(review_text: str) -> str:
    lines = [line.strip() for line in review_text.splitlines() if line.strip()]
    ready = [line for line in lines if READY_LINE.fullmatch(line)]
    negative = [line for line in lines if NEGATIVE_LINE.match(line)]
    if len(ready) != 1 or negative or not READY_LINE.fullmatch(lines[-1]):
        raise ReviewAdjudicationError(
            "review does not end in one unopposed exact READY TO FREEZE line"
        )
    return "READY TO FREEZE"


def _review_packet_artifacts(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    observed = manifest.get("artifacts")
    if not isinstance(observed, list) or len(observed) != len(REVIEW_PACKET):
        raise ReviewAdjudicationError("provider review artifact inventory differs")
    normalized: list[dict[str, Any]] = []
    for row, (relative, role) in zip(observed, REVIEW_PACKET):
        if not isinstance(row, Mapping):
            raise ReviewAdjudicationError("provider review artifact row differs")
        source = (Path(__file__).resolve().parents[2] / relative).resolve(strict=True)
        if (
            Path(str(row.get("path"))).resolve(strict=True) != source
            or row.get("role") != role
            or row.get("bytes") != source.stat().st_size
            or row.get("sha256") != protocol.sha256_file(source)
        ):
            raise ReviewAdjudicationError(
                f"provider did not review the frozen artifact: {relative}"
            )
        normalized.append(
            {
                "path": relative,
                "role": role,
                "bytes": source.stat().st_size,
                "sha256": protocol.sha256_file(source),
            }
        )
    return normalized


def build(
    *,
    review_dir: Path,
    plan_dir: Path,
    decisions_path: Path,
    output_relative_path: str,
) -> dict[str, Any]:
    directory = review_dir.expanduser().resolve(strict=True)
    review_path = directory / "review.md"
    response_path = directory / "response.json"
    manifest_path = directory / "review_manifest.json"
    response = _json(response_path)
    manifest = _json(manifest_path)
    verdict = terminal_verdict(review_path.read_text(encoding="utf-8"))
    reviewed_artifacts = _review_packet_artifacts(manifest)
    reviewed_commit = str(manifest.get("reviewed_packet_git_head_commit", ""))
    if (
        response.get("status") != "completed"
        or response.get("model") != "gpt-5.6-sol"
        or manifest.get("status") != "completed"
        or manifest.get("model") != "gpt-5.6-sol"
        or manifest.get("official_latest_model") != "gpt-5.6-sol"
        or manifest.get("response_model") != "gpt-5.6-sol"
        or manifest.get("response_id") != response.get("id")
        or manifest.get("review_scope") != EXPECTED_REVIEW_SCOPE
        or COMMIT_RE.fullmatch(reviewed_commit) is None
    ):
        raise ReviewAdjudicationError("provider review identity/completion differs")
    plan_manifest_path = plan_dir.expanduser().resolve(strict=True) / "plan_manifest.json"
    plan_manifest = _json(plan_manifest_path)
    plan_core = dict(plan_manifest)
    plan_hash = plan_core.pop("plan_manifest_sha256", None)
    if plan_hash != protocol.canonical_sha256(plan_core):
        raise ReviewAdjudicationError("final plan manifest self-hash differs")
    decisions_value = _json(decisions_path)
    decisions = decisions_value.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise ReviewAdjudicationError("review decisions are absent")
    unresolved: list[str] = []
    normalized: list[dict[str, Any]] = []
    for row in decisions:
        if not isinstance(row, Mapping):
            raise ReviewAdjudicationError("review decision row differs")
        disposition = row.get("disposition")
        finding_id = row.get("finding_id")
        if disposition not in {"accept", "accepted_modified", "reject", "defer"}:
            raise ReviewAdjudicationError("review disposition differs")
        if not isinstance(finding_id, str) or not finding_id:
            raise ReviewAdjudicationError("review finding ID is absent")
        if disposition == "defer" and row.get("blocks_execution") is not False:
            unresolved.append(finding_id)
        normalized.append(dict(row))
    core = {
        "schema_version": 1,
        "status": (
            "adjudicated_ready_to_execute" if not unresolved else "blocked"
        ),
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "receipt_path": output_relative_path,
        "review_model": "gpt-5.6-sol",
        "review_mode": "pro",
        "review_response_id": response["id"],
        "reviewed_packet_git_head_commit": reviewed_commit,
        "provider_verdict": verdict,
        "reviewed_packet_artifacts": reviewed_artifacts,
        "final_plan_manifest_sha256": plan_hash,
        "review_artifacts": [
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": protocol.sha256_file(path),
            }
            for path in (review_path, response_path, manifest_path)
        ],
        "decisions": normalized,
        "unresolved_blockers": unresolved,
        "limitations": [
            "provider reviewed the compact director packet, not raw data",
            "provider did not inspect or certify source, tests, GPU execution, or receipts",
            "small-model and B200 gates remain separate mechanical evidence",
        ],
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        relative = args.output.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError as exc:
        raise ReviewAdjudicationError("output must be inside the repository") from exc
    value = build(
        review_dir=args.review_dir,
        plan_dir=args.plan_dir,
        decisions_path=args.decisions,
        output_relative_path=relative,
    )
    if args.output.exists():
        raise ReviewAdjudicationError("adjudication output must be fresh")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(protocol.canonical_json_bytes(value) + b"\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
