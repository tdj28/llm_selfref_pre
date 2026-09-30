#!/usr/bin/env python3
"""Compile every tracked Python source without writing bytecode or importing it."""

from __future__ import annotations

import subprocess
from pathlib import Path


def check_sources(repo: Path) -> list[str]:
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "*.py"], cwd=repo
    ).decode().split("\0")
    failures = []
    count = 0
    for relative in filter(None, paths):
        count += 1
        try:
            compile((repo / relative).read_bytes(), relative, "exec")
        except (SyntaxError, OSError) as error:
            failures.append(f"{relative}: {error}")
    print(f"Checked {count} tracked Python sources; {len(failures)} failures")
    return failures


if __name__ == "__main__":
    errors = check_sources(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    raise SystemExit(bool(errors))
