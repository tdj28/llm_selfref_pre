#!/usr/bin/env python3
"""Read-only exact Kolibri replay diagnostic; not publication acceptance."""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
from statistics import NormalDist
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    from scripts.diagnose_repeat_release import canonical, differences, sha
finally:
    sys.path.remove(str(ROOT))

RELEASE = "data/kolibri_swap/release_v1_20261005"
MANIFEST_SHA = "78529659edb09af027e008e3d0513440933e8a560d4fe82c37718034e45e9ddf"
RELEASE_COMMIT = "3900a5ede5e6c003320960159e69811530f5346c"
REPORTER = "experiments/kolibri_release.py"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def regular(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink in diagnostic input")
    require(path.is_file() and path.stat().st_nlink == 1, "Missing/nonregular diagnostic input")
    return path.read_bytes()


def relative(name):
    path = Path(name)
    require(type(name) is str and path.as_posix() == name and not path.is_absolute()
            and ".." not in path.parts and "\\" not in name and ":" not in name,
            "Unsafe diagnostic inventory path")
    return path


def bound_inputs(root):
    source = root / RELEASE
    manifest_raw = regular(source / "MANIFEST.json")
    require(sha(manifest_raw) == MANIFEST_SHA, "Release manifest anchor changed")
    manifest = json.loads(manifest_raw)
    require(manifest["schema"] == "kolibri-release-manifest-v1", "Release manifest schema changed")
    names = {"MANIFEST.json"}
    for entry in manifest["files"]:
        name = entry["path"]
        require(name not in names, "Duplicate diagnostic inventory entry")
        raw = regular(source / relative(name))
        require(len(raw) == entry["bytes"] and sha(raw) == entry["sha256"], "Bound release artifact changed")
        names.add(name)
    actual = set()
    for path in source.rglob("*"):
        require(not path.is_symlink() and (path.is_dir() or path.is_file()), "Nonregular release entry")
        if path.is_file():
            actual.add(path.relative_to(source).as_posix())
    require(actual == names, "Release inventory changed")
    exporter = json.loads(regular(source / "EXPORTER.json"))
    require(exporter["schema"] == "kolibri-exporter-v1" and REPORTER in exporter["source_hashes"],
            "Exporter provenance changed")
    for name, expected in exporter["source_hashes"].items():
        require(sha(regular(root / relative(name))) == expected, "Bound exporter source changed")
    return manifest_raw, names, exporter


def load_reporter(root):
    sys.path.insert(0, str(root))
    try:
        reporter = importlib.import_module("experiments.kolibri_release")
    finally:
        sys.path.remove(str(root))
    require(Path(reporter.__file__).resolve() == root / REPORTER, "Reporter imported from another checkout")
    return reporter


def pointer_type(value, pointer):
    for key in pointer.split("/")[1:]:
        key = key.replace("~1", "/").replace("~0", "~")
        try:
            value = value[int(key)] if type(value) is list else value[key]
        except (KeyError, IndexError):
            return "absent"
    return type(value).__name__


def compare(name, saved_raw, replay):
    saved = json.loads(saved_raw)
    delta = differences(saved, replay)
    for row in delta:
        row.update(file=name, saved_type=pointer_type(saved, row["path"]),
                   replay_type=pointer_type(replay, row["path"]))
    return {"saved_file_sha256": sha(saved_raw), "saved_canonical_sha256": sha(canonical(saved).encode()),
            "replay_canonical_sha256": sha(canonical(replay).encode()), "exact_typed_replay": not delta,
            "frozen_comparison_equal": saved == replay, "difference_count": len(delta)}, delta


def diagnose(root=ROOT):
    root = Path(root).resolve()
    manifest_raw, names, exporter = bound_inputs(root)
    reporter = load_reporter(root)
    require(set(exporter["source_hashes"]) == set((*reporter.SOURCES, *reporter.DEPENDENCIES)),
            "Exporter source inventory changed")
    source = root / RELEASE
    inventory = reporter.inventory(source)
    reporter.allowed(source, inventory)
    with TemporaryDirectory(prefix="kolibri-release-diagnostic-") as temporary:
        snapshot = Path(temporary).resolve()
        for name in names:
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(regular(source / name))
        derived = reporter.derive(snapshot)
        require(set(derived) == reporter.JSON_OUTPUTS, "Derived JSON inventory changed")
        images = {name: regular(snapshot / name) for name in ("figures/cells.png", "figures/primary.png")}
        replay = {**derived, "FIGURES.json": reporter.figure_receipts(derived, images)}
        summary = reporter.summary(derived)
    files, delta = {}, []
    for name, value in sorted(replay.items()):
        files[name], changes = compare(name, regular(source / name), value)
        delta.extend(changes)
    saved_summary = regular(source / "SUMMARY.md")
    require(bound_inputs(root) == (manifest_raw, names, exporter), "Inputs changed during diagnostic")
    versions = {}
    for name in ("numpy", "scipy", "matplotlib", "pillow"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    seed = os.environ.get("PYTHONHASHSEED", "unset")
    z = NormalDist().inv_cdf(0.975)
    return {"schema": "kolibri-release-exact-diagnostic-v1", "manifest_sha256": MANIFEST_SHA,
            "release_commit": RELEASE_COMMIT, "exporter_source_hashes": exporter["source_hashes"],
            "python": platform.python_version(), "system": platform.system(), "machine": platform.machine(),
            "libc": list(platform.libc_ver()), "versions": versions,
            "normal_dist_z": z, "normal_dist_z_hex": z.hex(),
            "python_hash_seed": seed if seed in ("unset", "random") or seed.isdigit() else "unreported",
            "exact_replay": not delta and summary == saved_summary,
            "frozen_derived_comparison_equal": all(files[n]["frozen_comparison_equal"] for n in derived),
            "difference_count": len(delta), "files": files, "differences": delta,
            "summary": {"exact": summary == saved_summary, "saved_sha256": sha(saved_summary),
                        "replay_sha256": sha(summary)},
            "scope": "Diagnostic only; no tolerance, normalization, rendering, or publication acceptance"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    def offline(event, arguments):
        if event in ("socket.connect", "socket.getaddrinfo", "socket.bind"):
            raise RuntimeError("Network forbidden in release diagnostic")
    sys.addaudithook(offline)
    try:
        result = diagnose(args.root)
    except Exception as exc:
        # Unexpected exception messages can contain raw responses or local paths.
        print(canonical({"diagnostic_error": type(exc).__name__,
                         "message": "Bound diagnostic failed before a complete comparison"}))
        return 2
    print(canonical(result))
    return 0 if result["exact_replay"] else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
