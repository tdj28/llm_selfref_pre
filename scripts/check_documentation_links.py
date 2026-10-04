#!/usr/bin/env python3
"""Check local Markdown links and explicit repository paths, without network IO."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    "README.md", "AGENTS.md", "todo.md", "worst_case.md", "DATA_ARTIFACTS.md",
    "docs/README.md", "docs/CLAIM_LEDGER.md", "docs/REPRODUCTION.md",
    "docs/STUDY_INVENTORY.md", "data/README.md", "experiments/README.md",
    "scripts/README.md", "tests/README.md", "evidence/README.md",
    "paper/README.md", "provenance/README.md", "technical_blog_posts/README.md",
    "experiments/causal_transplant/README.md", "reviews/README.md",
)
GENERATED_PATHS = {"paper/main.pdf": ("paper/main.tex", "Makefile")}


def broken_references(repo: Path, document: Path) -> list[str]:
    text = document.read_text(encoding="utf-8")
    failures = []
    for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", text):
        url = urlsplit(target.strip("<>"))
        if url.scheme or url.netloc or not url.path:
            continue
        if not (document.parent / unquote(url.path)).exists():
            failures.append(target)
    # Abbreviated table paths such as analysis/foo.csv need human context.
    # Check only references that explicitly name a repository-root namespace.
    for target in re.findall(r"`((?:data|docs|experiments|paper|src|scripts)/[^`\n]+)`", text):
        # A documented build output need not exist before its build runs.
        # Actual Markdown links still require a destination above.
        if target in GENERATED_PATHS and all((repo / path).is_file() for path in GENERATED_PATHS[target]):
            continue
        if not any(repo.glob(target)):
            failures.append(target)
    return sorted(set(failures))


if __name__ == "__main__":
    errors = []
    for relative in DOCUMENTS:
        errors.extend(f"{relative}: {target}" for target in broken_references(ROOT, ROOT / relative))
    for error in errors:
        print(error)
    print(f"Checked {len(DOCUMENTS)} documentation files; {len(errors)} broken references")
    raise SystemExit(bool(errors))
