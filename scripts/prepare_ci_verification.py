#!/usr/bin/env python3
"""Prepare the current Ubuntu CI jobs without editing source-bound verify.yml.

The frozen tests job already checks out full history and installs CPU Python
dependencies; it additionally needs Poppler. The frozen paper-evidence job is
shallow and has no dependencies, so its current Make target prepares both.
Outside GitHub Actions this helper does nothing. It never checks out another
revision, rewrites a scientific source, runs a verifier, or downloads models.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
POPPLER = ("pdffonts", "pdftohtml", "pdfimages", "pdftotext")


def command(args, *, root, timeout, capture=False):
    result = subprocess.run(args, cwd=root, check=True, text=True,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE if capture else None, timeout=timeout)
    return result.stdout.strip() if capture else None


def prepare(mode, *, root=ROOT, environ=None, platform=sys.platform,
            run=command, which=shutil.which, python=sys.executable):
    if mode not in {"tests", "paper"}:
        raise ValueError("Unknown verification job")
    env = os.environ if environ is None else environ
    if env.get("GITHUB_ACTIONS") != "true":
        return {"prepared": False, "reason": "not_github_actions"}
    if platform != "linux":
        raise ValueError("The frozen Verify jobs require Ubuntu/Linux")
    root = Path(root).resolve()
    if mode == "paper":
        args = ["git", "rev-parse", "--is-shallow-repository"]
        shallow = run(args, root=root, timeout=30, capture=True)
        if shallow not in {"true", "false"}:
            raise ValueError("Cannot determine checkout depth")
        if shallow == "true":
            head = run(["git", "rev-parse", "--verify", "HEAD"], root=root, timeout=30, capture=True)
            if re.fullmatch(r"[0-9a-f]{40}", head) is None:
                raise ValueError("Cannot bind the checked-out commit")
            # Include the detached PR merge SHA as well as branch/tag history.
            run(["git", "fetch", "--unshallow", "--no-recurse-submodules", "--tags", "origin",
                 "+refs/heads/*:refs/remotes/origin/*", head],
                root=root, timeout=300)
            if run(args, root=root, timeout=30, capture=True) != "false":
                raise ValueError("Historical Git objects still have a shallow boundary")
            if run(["git", "rev-parse", "--verify", "HEAD"], root=root, timeout=30, capture=True) != head:
                raise ValueError("CI preparation changed the checked-out commit")
    if any(which(tool) is None for tool in POPPLER):
        run(["sudo", "apt-get", "update"], root=root, timeout=120)
        run(["sudo", "apt-get", "install", "--yes", "--no-install-recommends", "poppler-utils"],
            root=root, timeout=180)
        if any(which(tool) is None for tool in POPPLER):
            raise ValueError("Poppler tools remain unavailable")
    if mode == "paper":
        run([python, "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements-ci.txt"],
            root=root, timeout=300)
        run([python, "-m", "pip", "check"], root=root, timeout=60)
    return {"prepared": True, "job": mode, "poppler": list(POPPLER),
            "python_dependencies": "requirements-ci.txt" if mode == "paper" else "existing_workflow_install",
            "git_history": "full" if mode == "paper" else "existing_workflow_fetch_depth_0"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", choices=("tests", "paper"))
    args = parser.parse_args(argv)
    try:
        print(json.dumps(prepare(args.job), sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("CI environment preparation failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
