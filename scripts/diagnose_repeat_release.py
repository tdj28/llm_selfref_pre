#!/usr/bin/env python3
"""Offline exact-diff diagnostic, not a replacement release verifier.

Replay the released repeated-study reporter in a disposable copy after checking
its manifest and reporter source hashes. Print differences without accepting a
tolerance, changing any source/result bytes, or contacting a service. A mismatch
exits 1; invalid inputs or a failed replay exit 2. No collection is authorized.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import platform
import struct
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "data/repeated_swap/completed_v1_20261005"
MANIFEST_SHA = "c0d44ab369739425645475ef1e62281c7615982c5288b6d0cc4a0b2ba36c75cf"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _value(value):
    if isinstance(value, (dict, list, str)):
        return {"type": type(value).__name__, "sha256": sha(canonical(value).encode())}
    return value


def _ordered_float(value):
    bits = struct.unpack(">Q", struct.pack(">d", value))[0]
    return ~bits & ((1 << 64) - 1) if bits >> 63 else bits | (1 << 63)


def differences(saved, replay, path=""):
    """Exact typed JSON comparison, with float diagnostics but no tolerance."""
    if canonical(saved) == canonical(replay) and type(saved) is type(replay):
        return []
    if type(saved) is not type(replay):
        return [{"path": path, "kind": "type", "saved": _value(saved), "replay": _value(replay),
                 "saved_type": type(saved).__name__, "replay_type": type(replay).__name__}]
    result = []
    if isinstance(saved, dict):
        for key in sorted(saved.keys() | replay.keys()):
            child = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if key not in saved or key not in replay:
                result.append({"path": child, "kind": "key", "saved_present": key in saved,
                               "replay_present": key in replay})
            else:
                result.extend(differences(saved[key], replay[key], child))
        return result
    if isinstance(saved, list):
        if len(saved) != len(replay):
            result.append({"path": path, "kind": "length", "saved": len(saved), "replay": len(replay)})
        for index, (a, b) in enumerate(zip(saved, replay)):
            result.extend(differences(a, b, path + "/" + str(index)))
        return result
    item = {"path": path, "kind": type(saved).__name__, "saved": _value(saved), "replay": _value(replay)}
    if type(saved) is float:
        item.update(absolute_error=abs(saved - replay),
                    ulp_distance=abs(_ordered_float(saved) - _ordered_float(replay)),
                    saved_hex=saved.hex(), replay_hex=replay.hex())
    return [item]


def diagnose(root=ROOT):
    root = Path(root).resolve()
    sys.path.insert(0, str(root))
    reporter = importlib.import_module("experiments.repeat_funding_release_a1")
    if Path(reporter.__file__).resolve() != root / "experiments/repeat_funding_release_a1.py":
        raise ValueError("Reporter imported from a different checkout")
    source = root / RELEASE
    base, p = reporter.base, reporter.p
    base._no_symlinks(source)
    inventory = reporter._inventory(source, derived=True)
    manifest_bytes = (source / "MANIFEST.json").read_bytes()
    manifest = base._load(source / "MANIFEST.json")
    if sha(manifest_bytes) != MANIFEST_SHA or manifest_bytes != (p.canonical(manifest) + "\n").encode():
        raise ValueError("Release manifest anchor or encoding differs")
    entries = base._entries(source)
    if manifest != {"schema": reporter.MANIFEST_SCHEMA, "files": entries}:
        raise ValueError("Release inventory or bytes differ")
    metadata = base._load(source / "RELEASE.json")
    for name in reporter.OWN_SOURCES:
        if sha((root / name).read_bytes()) != metadata["source_hashes"][name]:
            raise ValueError("Released reporter source differs: " + name)
    with TemporaryDirectory(prefix="repeat-release-diagnostic-") as temporary:
        snapshot = Path(temporary).resolve()
        for name in set(inventory) - reporter.DERIVED - reporter.A2_DERIVED - reporter.A3_DERIVED:
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source / name).read_bytes())
        expected = reporter._derive(snapshot)
    files, diffs = {}, []
    for name, replay in sorted(expected.items()):
        saved = base._load(source / name)
        delta = differences(saved, replay, name)
        files[name] = {"saved_file_sha256": sha((source / name).read_bytes()),
                       "saved_canonical_sha256": sha(p.canonical(saved).encode()),
                       "replay_canonical_sha256": sha(p.canonical(replay).encode()),
                       "exact": not delta, "difference_count": len(delta)}
        diffs.extend(delta)
    if base._entries(source) != entries or (source / "MANIFEST.json").read_bytes() != manifest_bytes:
        raise ValueError("Release changed during diagnostic")
    return {"schema": "repeated-release-exact-diagnostic-v1", "manifest_sha256": MANIFEST_SHA,
            "python": platform.python_version(), "system": platform.system(),
            "machine": platform.machine(), "libc": list(platform.libc_ver()),
            "exact_replay": not diffs, "difference_count": len(diffs), "files": files,
            "differences": diffs, "scope": "Diagnostic only; no tolerance or publication acceptance"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        result = diagnose(args.root)
    except Exception as exc:
        print(canonical({"diagnostic_error": type(exc).__name__, "message": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result["exact_replay"] else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
