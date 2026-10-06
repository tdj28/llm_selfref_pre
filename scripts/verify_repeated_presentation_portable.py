#!/usr/bin/env python3
"""Read-only case-sensitive entry point; the bound presentation source is unchanged."""
from contextlib import contextmanager
import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import verify_repeated_presentation as original

SOURCE_SHA = "df141ee6a908f79a39a4487fc88c61a1d1e1e3caa3dfcb3f094e513042b5cbd5"
derive = original.derive


def load(root=ROOT):
    original.require(original.sha((ROOT / "scripts/verify_repeated_presentation.py").read_bytes())
                     == SOURCE_SHA, "Bound presentation verifier changed")
    # Use the tracked spelling, never a case-insensitive fallback or a second copy.
    raw = (root / original.SOURCE / "MANIFEST.json").read_bytes()
    original.require(original.sha(raw) == original.SOURCE_SHA,
                     "Original publication manifest changed")
    for entry in json.loads(raw)["files"]:
        body = (root / original.SOURCE / entry["path"]).read_bytes()
        original.require(len(body) == entry["bytes"] and original.sha(body) == entry["sha256"],
                         "Original publication output changed: " + entry["path"])
    return (json.loads((root / original.SOURCE / "figure_data.json").read_bytes()),
            json.loads((root / original.SOURCE / "binding.json").read_bytes()))


@contextmanager
def portable_load():
    with patch.object(original, "load", load):
        yield


def verify(root=ROOT, *, rerender=False):
    with portable_load():
        return original.verify(root, rerender=rerender)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rerender", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(verify(rerender=args.rerender), sort_keys=True))


if __name__ == "__main__":
    main()
