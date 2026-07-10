#!/usr/bin/env python3
"""Hash and audit the public causal-experiment release bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def is_private_name(name: str) -> bool:
    return (name.startswith("annotation_key") and "_private.csv" in name) or name.startswith(
        "coder_"
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_commit(repo_root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def audit_jsonl(path: Path, id_field: str) -> dict[str, Any]:
    rows = read_jsonl(path)
    identifiers = [str(row.get(id_field, "")) for row in rows]
    return {
        "rows": len(rows),
        "id_field": id_field,
        "unique_ids": len(set(identifiers)),
        "duplicate_ids": len(identifiers) - len(set(identifiers)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    output = run_dir / "release_manifest.json"

    files = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path == output or is_private_name(path.name):
            continue
        files.append(
            {
                "path": str(path.relative_to(run_dir)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    audits = {
        "induction_bank.jsonl": audit_jsonl(run_dir / "induction_bank.jsonl", "induction_id"),
        "outcomes.jsonl": audit_jsonl(run_dir / "outcomes.jsonl", "trial_id"),
        "judgments_paper.jsonl": audit_jsonl(
            run_dir / "judgments_paper.jsonl", "judgment_id"
        ),
        "judgments_construct.jsonl": audit_jsonl(
            run_dir / "judgments_construct.jsonl", "judgment_id"
        ),
    }
    outcomes = read_jsonl(run_dir / "outcomes.jsonl")
    empty_outcomes = [row["trial_id"] for row in outcomes if not row.get("final_output", "").strip()]
    manifest = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": current_commit(repo_root),
        "run_directory": str(run_dir.relative_to(repo_root)),
        "audits": audits,
        "empty_outcome_count": len(empty_outcomes),
        "empty_outcome_trial_ids": empty_outcomes,
        "historical_judge_error_rows": sum(
            1
            for _ in (run_dir / "judgments_construct.errors.jsonl").open(encoding="utf-8")
        ),
        "private_files_excluded": sorted(
            path.name for path in run_dir.iterdir() if path.is_file() and is_private_name(path.name)
        ),
        "files": files,
    }
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {output} with {len(files)} file hashes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
