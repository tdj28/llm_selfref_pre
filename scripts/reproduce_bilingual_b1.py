"""Filesystem preflight around the unchanged, frozen B1 reproduction code.

Added after outcomes began. It changes neither labels nor statistical analysis.
Inputs must be closed, immutable snapshots; this is not an atomic snapshotter.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.bilingual_llama_b1 import release


def no_link_chain(path):
    path = Path(path).absolute()
    for entry in (path, *path.parents):
        if entry.is_symlink():
            raise ValueError("Symlinked input or destination: " + str(entry))
    return path


def regular_tree(root):
    root = no_link_chain(root)
    if not root.is_dir():
        raise ValueError("Input tree must be an existing directory")
    files = []
    for entry in root.rglob("*"):
        mode = entry.lstat().st_mode
        if stat.S_ISREG(mode):
            files.append(entry.relative_to(root).as_posix())
        elif not stat.S_ISDIR(mode):
            raise ValueError("Nonregular input entry: " + str(entry))
    return tuple(sorted(files))


def reproduce(raw_root, judge_root, plan, freeze, out):
    raw_root, judge_root = no_link_chain(raw_root), no_link_chain(judge_root)
    plan, out = no_link_chain(plan), no_link_chain(out)
    if not stat.S_ISREG(plan.lstat().st_mode):
        raise ValueError("Plan must be a regular file")
    before = (regular_tree(raw_root), regular_tree(judge_root))
    result = release.reproduce(raw_root, judge_root, plan, freeze, out)
    if before != (regular_tree(raw_root), regular_tree(judge_root)):
        raise ValueError("Input filesystem inventory changed during reproduction")
    return {**result, "input_tree_preflight": {
        "pass": True, "raw_files": len(before[0]), "judge_files": len(before[1])}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("raw-root", "judge-root", "plan", "freeze", "out"):
        parser.add_argument("--" + key, required=True)
    args = parser.parse_args()
    print(json.dumps(reproduce(args.raw_root, args.judge_root, args.plan,
                               args.freeze, args.out), sort_keys=True))


if __name__ == "__main__":
    main()
