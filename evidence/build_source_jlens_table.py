#!/usr/bin/env python3
"""Build a verified comparator table outside the immutable source evidence package.

An identical existing table is accepted; different existing content is never
overwritten. Optional --source-repo checks only local pinned Git objects.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verify_source_jlens_table", ROOT / "scripts/verify_source_jlens_table.py")
verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify)


def build(package=verify.source.DEFAULT_PACKAGE, output=verify.DEFAULT_TABLE, source_repo=None):
    output = Path(output)
    verify.outside_package(output, package)
    blob, _ = verify.render(package, source_repo)
    if output.exists():
        verify.source.require(output.read_bytes() == blob, "Refusing to overwrite a different existing table")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as stream:
            stream.write(blob)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=verify.source.DEFAULT_PACKAGE)
    parser.add_argument("--output", type=Path, default=verify.DEFAULT_TABLE)
    parser.add_argument("--source-repo", type=Path)
    args = parser.parse_args(argv)
    try:
        print(build(args.package, args.output, args.source_repo))
        return 0
    except (ValueError, KeyError, TypeError, OSError, verify.InvalidOperation) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
