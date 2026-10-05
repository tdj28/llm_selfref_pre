"""Exact-pair, post-outcome reporting adapter; never collection or generic tolerance."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys
from threading import RLock

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "data/repeated_swap/completed_v1_20261005"
PACKAGE = "evidence/repeated_extension"
BINDING = "evidence/repeated_extension_row_binding.json"
EVIDENCE = ROOT / "provenance/repeated_release_portability.json"
EVIDENCE_SHA = "5273a316e1098db883fe77c47b07b667c81387cdfc35bb22f35134124b085518"
MANIFEST_SHA = "c0d44ab369739425645475ef1e62281c7615982c5288b6d0cc4a0b2ba36c75cf"
PACKAGE_SHA = "b2cd569022042097cf574f2dd7038cad20489a6b43992eeb01f631357ff5e242"
BINDING_SHA = "988ea040704053bd3e1291bb5fffba772d6df4ede6b0bfb69a5907a3f7dae907"
SAVED_SHA = "8ea6510043ac397c819758e0a668bdc158648d4803987c1347bb3aad30f8aaf5"
LINUX_SHA = "8d02c067245bc871972a4c2d64a2283cd53797da076a1423917fa4c214a987c9"
ROWS_SHA = "60f81e4ff77042035eb8d6a2ce702832cd6f0c9965272ff45f7a358b26337f07"
SAVED_HEX = "-0x1.f86a314dbf868p-6"
LINUX_HEX = "-0x1.f86a314dbf867p-6"
FIELD = ("models", "gemini", "judges", "opus", "paper", "variance", "SH", "bootstrap", "B_interval")
_LOCK = RLock()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def value_sha(value):
    return sha(canonical(value).encode())


def regular(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink in portability input")
    require(path.is_file(), "Missing portability input")
    return path.read_bytes()


def observations(path=EVIDENCE):
    raw = regular(path)
    require(sha(raw) == EVIDENCE_SHA, "Archived CI diagnostic sidecar changed")
    evidence = json.loads(raw)
    reports = [row["diagnostic"] for row in evidence["observations"]]
    require(len(reports) == 2 and reports[0]["differences"] == reports[1]["differences"]
            and reports[0]["files"] == reports[1]["files"], "CI observations disagree")
    return evidence, reports[0]["files"]


def _manifest(root, expected):
    raw = regular(root / "MANIFEST.json")
    require(sha(raw) == expected, "Portability manifest anchor changed")
    manifest = json.loads(raw)
    names = {"MANIFEST.json"}
    for entry in manifest["files"]:
        name = entry["path"]
        path = Path(name)
        require(not path.is_absolute() and ".." not in path.parts and path.as_posix() == name,
                "Unsafe portability inventory path")
        blob = regular(root / name)
        require(len(blob) == entry["bytes"] and sha(blob) == entry["sha256"], "Bound artifact changed: " + name)
        names.add(name)
    actual = set()
    for path in root.rglob("*"):
        require(not path.is_symlink(), "Symlink in portability inventory")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
        else:
            require(path.is_dir(), "Nonregular portability inventory entry")
    require(actual == names, "Portability inventory changed")


def verify_inputs(root=ROOT, evidence_path=EVIDENCE):
    root = Path(root).resolve()
    evidence, files = observations(evidence_path)
    _manifest(root / RELEASE, MANIFEST_SHA)
    _manifest(root / PACKAGE, PACKAGE_SHA)
    binding_raw = regular(root / BINDING)
    require(sha(binding_raw) == BINDING_SHA, "Published row binding changed")
    records = [json.loads(regular(root / RELEASE / "PLAN.json")),
               json.loads(regular(root / RELEASE / "RELEASE.json")),
               json.loads(regular(root / PACKAGE / "binding.json")), json.loads(binding_raw)]
    hashes = {}
    for record in records:
        for name, expected in record["source_hashes"].items():
            require(name not in hashes or hashes[name] == expected, "Conflicting original source hashes")
            require(sha(regular(root / name)) == expected, "Bound scientific/reporting source changed: " + name)
            hashes[name] = expected
    for name, entry in files.items():
        raw = regular(root / RELEASE / name)
        require(sha(raw) == entry["saved_file_sha256"]
                and value_sha(json.loads(raw)) == entry["saved_canonical_sha256"],
                "Archived derived-file anchor changed: " + name)
    return evidence


def _interval(analysis):
    value = analysis
    for key in FIELD:
        value = value[key]
    require(type(value) is list and len(value) == 2
            and all(type(v) is float and math.isfinite(v) for v in value), "Bound interval type changed")
    return value


def normalize_analysis(replay):
    """Accept only the two measured entire outputs; preserve the saved analysis."""
    observed_sha = value_sha(replay)
    require(observed_sha in (SAVED_SHA, LINUX_SHA), "Unmeasured whole-analysis output")
    interval = _interval(replay)
    expected_hex = SAVED_HEX if observed_sha == SAVED_SHA else LINUX_HEX
    require(interval[0].hex() == expected_hex, "Unmeasured interval float pair")
    saved_lower = float.fromhex(SAVED_HEX)
    require(interval[0] <= interval[1] and saved_lower <= interval[1]
            and (interval[0] <= 0 <= interval[1]) == (saved_lower <= 0 <= interval[1])
            and (interval[0] < 0) == (saved_lower < 0), "Interval ordering or zero-crossing changed")
    result = deepcopy(replay)
    _interval(result)[0] = saved_lower
    require(value_sha(result) == SAVED_SHA, "A field outside the measured float pair changed")
    return result, {"observed_analysis_sha256": observed_sha, "canonical_saved_analysis_sha256": SAVED_SHA,
                    "exact_replay": observed_sha == SAVED_SHA,
                    "accepted_known_float_pair": observed_sha == LINUX_SHA}


@contextmanager
def portable_replay(root=ROOT, evidence_path=EVIDENCE):
    """Scope one in-memory analysis wrapper; all original verifier code still runs."""
    root = Path(root).resolve()
    with _LOCK:
        verify_inputs(root, evidence_path)
        sys.path.insert(0, str(root))
        try:
            analysis = importlib.import_module("experiments.repeated_swap.analysis")
            reporter = importlib.import_module("experiments.repeat_funding_release_a1")
            require(Path(analysis.__file__).resolve() == root / "experiments/repeated_swap/analysis.py",
                    "Analysis imported from a different checkout")
            require(Path(reporter.__file__).resolve() == root / "experiments/repeat_funding_release_a1.py",
                    "Reporter imported from a different checkout")
            original = analysis.analyze
            strict_verify = reporter.verify
            require(not getattr(original, "_repeat_portability", False), "Nested portability context")
            enabled = True
            report = {"policy": "exact manifest, row inventory, float pair and whole-analysis hashes only",
                      "evidence_sha256": EVIDENCE_SHA, "manifest_sha256": MANIFEST_SHA,
                      "original_ci_exact_replay": "FAIL", "local_replays": []}
            def analyze(rows, phase="main"):
                result = original(rows, phase)
                if enabled and phase == "main" and type(rows) is list and value_sha(rows) == ROWS_SHA:
                    result, check = normalize_analysis(result)
                    report["local_replays"].append(check)
                return result
            def verify(destination, *, manifest_sha256=None):
                nonlocal enabled
                previous = enabled
                enabled = (sha(regular(Path(destination) / "MANIFEST.json")) == MANIFEST_SHA
                           and manifest_sha256 in (None, MANIFEST_SHA))
                try:
                    return strict_verify(destination, manifest_sha256=manifest_sha256)
                finally:
                    enabled = previous
            analyze._repeat_portability = True
            analysis.analyze = analyze
            reporter.verify = verify
            try:
                yield report
            finally:
                analysis.analyze = original
                reporter.verify = strict_verify
                verify_inputs(root, evidence_path)
        finally:
            sys.path.remove(str(root))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true")
    args, forwarded = parser.parse_known_args(argv)
    require(not args.write, "Portable entrypoint is verification-only")
    def offline(event, arguments):
        if event in ("socket.connect", "socket.getaddrinfo", "socket.bind"):
            raise RuntimeError("Network is forbidden in portable verification")
    sys.addaudithook(offline)
    with portable_replay(args.root) as report:
        verifier = importlib.import_module("scripts.verify_repeated_extension")
        require(Path(verifier.__file__).resolve() == args.root.resolve() / "scripts/verify_repeated_extension.py",
                "Verifier imported from a different checkout")
        verifier.main(forwarded)
    print(canonical({"repeated_release_portability": report}))
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
