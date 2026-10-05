"""Bound numerical-pair and lossless PNG encoding adapters; no generic tolerance."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from threading import RLock

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "data/repeated_swap/completed_v1_20261005"
PACKAGE = "evidence/repeated_extension"
BINDING = "evidence/repeated_extension_row_binding.json"
EVIDENCE = ROOT / "provenance/repeated_release_portability.json"
EVIDENCE_SHA = "5273a316e1098db883fe77c47b07b667c81387cdfc35bb22f35134124b085518"
PNG_EVIDENCE = ROOT / "provenance/repeated_png_encoding.json"
PNG_EVIDENCE_SHA = "3b3b70d1672bf4432bf254b5d3574a6a531f5076ea3600a6b7e8e6fac6307532"
PNG_NAMES = ("repeated_main.png", "repeated_effects.png")
MANIFEST_SHA = "c0d44ab369739425645475ef1e62281c7615982c5288b6d0cc4a0b2ba36c75cf"
PACKAGE_SHA = "b2cd569022042097cf574f2dd7038cad20489a6b43992eeb01f631357ff5e242"
BINDING_SHA = "988ea040704053bd3e1291bb5fffba772d6df4ede6b0bfb69a5907a3f7dae907"
SAVED_SHA = "8ea6510043ac397c819758e0a668bdc158648d4803987c1347bb3aad30f8aaf5"
LINUX_SHA = "8d02c067245bc871972a4c2d64a2283cd53797da076a1423917fa4c214a987c9"
ROWS_SHA = "60f81e4ff77042035eb8d6a2ce702832cd6f0c9965272ff45f7a358b26337f07"
SAVED_HEX = "-0x1.f86a314dbf868p-6"
LINUX_HEX = "-0x1.f86a314dbf867p-6"
FIELD = ("models", "gemini", "judges", "opus", "paper", "variance", "SH", "bootstrap", "B_interval")
AUDITOR = "scripts/audit_public_release.py"
HISTORICAL_COMMIT = "033917d188602203cfbbe7717bf7ba704d44aed6"
HISTORICAL_AUDITOR_SHA = "97db36ab3d45eb9e59127b66ee96fce57897dc27aa5ce2349b60538171d5a1e6"
REVIEWED_AUDITOR_SHA = "51ef43e48907457daa903d1adc991fa9c3193ad2a8c41aabaca089466f286ced"
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


def verify_inputs(root=ROOT, evidence_path=EVIDENCE, *, historical_reporting=True):
    root = Path(root).resolve()
    evidence, files = observations(evidence_path)
    _manifest(root / RELEASE, MANIFEST_SHA)
    _manifest(root / PACKAGE, PACKAGE_SHA)
    binding_raw = regular(root / BINDING)
    require(sha(binding_raw) == BINDING_SHA, "Published row binding changed")
    records = [json.loads(regular(root / RELEASE / "PLAN.json")),
               json.loads(regular(root / RELEASE / "RELEASE.json")),
               json.loads(regular(root / PACKAGE / "binding.json")), json.loads(binding_raw)]
    records.extend(json.loads(regular(root / RELEASE / phase / "PLAN.json"))
                   for phase in ("funding_a1", "transport_a2", "refusal_a3"))
    hashes = {}
    history_checked = False
    for record in records:
        for name, expected in {**record["source_hashes"], **record.get("input_hashes", {})}.items():
            require(name not in hashes or hashes[name] == expected, "Conflicting original source hashes")
            actual = sha(regular(root / name))
            if historical_reporting and (name, expected, actual) == (AUDITOR, HISTORICAL_AUDITOR_SHA, REVIEWED_AUDITOR_SHA):
                if not history_checked:
                    historical_auditor(root)
                    history_checked = True
            else:
                require(actual == expected, "Bound scientific/reporting source changed: " + name)
            hashes[name] = expected
    for name, entry in files.items():
        raw = regular(root / RELEASE / name)
        require(sha(raw) == entry["saved_file_sha256"]
                and value_sha(json.loads(raw)) == entry["saved_canonical_sha256"],
                "Archived derived-file anchor changed: " + name)
    return evidence


def _historical_blob(root, name):
    # Local objects only; ignore ambient Git overrides and replacement objects.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(["git", "--no-replace-objects", "cat-file", "blob",
                             HISTORICAL_COMMIT + ":" + name], cwd=root, env=env,
                            capture_output=True, timeout=30, check=False)
    require(result.returncode == 0, "Required local historical reporting object unavailable; no fetch attempted")
    return result.stdout


def historical_auditor(root):
    """Authenticate one historical reporting input, never an arbitrary source override."""
    root = Path(root).resolve()
    current_sha = sha(regular(root / AUDITOR))
    require(current_sha in (HISTORICAL_AUDITOR_SHA, REVIEWED_AUDITOR_SHA),
            "Unapproved current public auditor")
    manifest = _historical_blob(root, RELEASE + "/MANIFEST.json")
    require(sha(manifest) == MANIFEST_SHA and manifest == regular(root / RELEASE / "MANIFEST.json"),
            "Historical release manifest changed")
    archived = _historical_blob(root, AUDITOR)
    require(sha(archived) == HISTORICAL_AUDITOR_SHA, "Historical public auditor changed")
    plan = regular(root / RELEASE / "PLAN.json")
    entries = json.loads(manifest)["files"]
    require(any(row["path"] == "PLAN.json" and row["sha256"] == sha(plan)
                and row["bytes"] == len(plan) for row in entries)
            and json.loads(plan)["source_hashes"].get(AUDITOR) == HISTORICAL_AUDITOR_SHA,
            "Historical plan auditor binding changed")
    return archived, {"scope": "offline reporting provenance only; current scanner remains active",
                      "release_commit": HISTORICAL_COMMIT, "manifest_sha256": MANIFEST_SHA,
                      "historical_auditor_sha256": HISTORICAL_AUDITOR_SHA,
                      "current_auditor_sha256": current_sha,
                      "original_exact_source_check": "PASS" if current_sha == HISTORICAL_AUDITOR_SHA else "FAIL",
                      "original_failure": "Bound scientific/reporting source changed: " + AUDITOR,
                      "historical_source_hash_reads": 0}


@contextmanager
def reporting_source_replay(root=ROOT, evidence_path=EVIDENCE):
    """Hash the verified Git blob for one provenance input; do not load old audit code."""
    root = Path(root).resolve()
    with _LOCK:
        verify_inputs(root, evidence_path)
        archived, record = historical_auditor(root)
        sys.path.insert(0, str(root))
        try:
            protocol = importlib.import_module("experiments.repeated_swap.protocol")
        finally:
            sys.path.remove(str(root))
        require(Path(protocol.__file__).resolve() == root / "experiments/repeated_swap/protocol.py",
                "Protocol imported from a different checkout")
        original = protocol.sha
        require(not getattr(original, "_repeat_reporting_history", False), "Nested reporting source context")
        def historical_sha(path):
            if Path(path).absolute() == root / AUDITOR:
                require(sha(regular(root / AUDITOR)) == record["current_auditor_sha256"],
                        "Public auditor changed during replay")
                record["historical_source_hash_reads"] += 1
                return sha(archived)
            return original(path)
        historical_sha._repeat_reporting_history = True
        protocol.sha = historical_sha
        try:
            yield record
        finally:
            protocol.sha = original
            require(sha(regular(root / AUDITOR)) == record["current_auditor_sha256"],
                    "Public auditor changed during replay")


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


def png_observations(path=PNG_EVIDENCE):
    raw = regular(path)
    require(sha(raw) == PNG_EVIDENCE_SHA, "Archived PNG diagnostic sidecar changed")
    evidence = json.loads(raw)
    reports = [row["diagnostic"] for row in evidence["observations"]]
    require(len(reports) == 2 and reports[0]["files"] == reports[1]["files"], "PNG CI observations disagree")
    for report in reports:
        require(report["publication_manifest_sha256"] == PACKAGE_SHA, "PNG observation package differs")
        for name, row in report["files"].items():
            require(row["exact"] if name.endswith(".pdf") else row["decoded"]["pixels_equal"],
                    "PNG observations do not establish lossless encoding differences")
    return evidence


def typed_equal(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return (all(type(key) is str for key in (*a, *b)) and a.keys() == b.keys()
                and all(typed_equal(a[key], b[key]) for key in a))
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(typed_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, float):
        return math.isfinite(a) and a.hex() == b.hex()
    return a == b


def png_equivalence(saved, replay):
    """Exact decoded content check, not an image-similarity threshold."""
    from PIL import Image

    def decode(raw):
        with Image.open(BytesIO(raw)) as image:
            require(image.format == "PNG", "PNG format changed")
            image.verify()
        with Image.open(BytesIO(raw)) as image:
            require(image.n_frames == 1, "PNG frame count changed")
            image.load()
            return image.mode, image.size, deepcopy(image.info), image.convert("RGBA").tobytes()
    a, b = decode(saved), decode(replay)
    require(a[0] == b[0], "PNG mode changed")
    require(a[1] == b[1], "PNG dimensions changed")
    require(typed_equal(a[2], b[2]), "PNG metadata changed")
    require(a[3] == b[3], "PNG pixels changed")
    return {"saved_png_sha256": sha(saved), "rendered_png_sha256": sha(replay),
            "exact_file_replay": saved == replay, "encoding_normalized": saved != replay,
            "rgba_sha256": sha(a[3]), "mode": a[0], "dimensions": list(a[1]), "metadata_exact": True}


@contextmanager
def portable_replay(root=ROOT, evidence_path=EVIDENCE, png_evidence_path=PNG_EVIDENCE):
    """Run original verifiers with scoped numerical and temporary PNG normalization."""
    root = Path(root).resolve()
    with _LOCK, reporting_source_replay(root, evidence_path) as source_history:
        verify_inputs(root, evidence_path)
        png_observations(png_evidence_path)
        sys.path.insert(0, str(root))
        try:
            analysis = importlib.import_module("experiments.repeated_swap.analysis")
            reporter = importlib.import_module("experiments.repeat_funding_release_a1")
            publication = importlib.import_module("experiments.repeat_publication")
            require(Path(analysis.__file__).resolve() == root / "experiments/repeated_swap/analysis.py",
                    "Analysis imported from a different checkout")
            require(Path(reporter.__file__).resolve() == root / "experiments/repeat_funding_release_a1.py",
                    "Reporter imported from a different checkout")
            require(Path(publication.__file__).resolve() == root / "experiments/repeat_publication.py",
                    "Publication renderer imported from a different checkout")
            original = analysis.analyze
            strict_verify = reporter.verify
            strict_publication = publication.verify
            original_render = publication._render
            original_temporary = publication.TemporaryDirectory
            require(not getattr(original, "_repeat_portability", False), "Nested portability context")
            enabled = True
            png_enabled, owned_temporary = False, None
            frozen_data = json.loads(regular(root / PACKAGE / "figure_data.json"))
            report = {"policy": "exact manifest, row inventory, float pair and whole-analysis hashes only",
                      "reporting_source_history": source_history,
                      "evidence_sha256": EVIDENCE_SHA, "manifest_sha256": MANIFEST_SHA,
                      "original_ci_exact_replay": "FAIL", "local_replays": [],
                      "png_policy": "bound figure data; exact mode, dimensions, typed metadata and RGBA bytes; PDFs stay byte-exact",
                      "png_evidence_sha256": PNG_EVIDENCE_SHA, "png_original_ci_exact_replay": "FAIL", "png_replays": []}
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
            def verify_publication(source, destination, *, release_manifest_sha256, manifest_sha256):
                nonlocal png_enabled
                previous = png_enabled
                png_enabled = (Path(source).resolve() == root / RELEASE
                               and Path(destination).resolve() == root / PACKAGE
                               and release_manifest_sha256 == MANIFEST_SHA and manifest_sha256 == PACKAGE_SHA)
                try:
                    return strict_publication(source, destination, release_manifest_sha256=release_manifest_sha256,
                                              manifest_sha256=manifest_sha256)
                finally:
                    png_enabled = previous
            @contextmanager
            def temporary(*args, **kwargs):
                nonlocal owned_temporary
                with original_temporary(*args, **kwargs) as name:
                    previous = owned_temporary
                    if png_enabled and kwargs.get("prefix") == "repeat-figure-verify-":
                        owned_temporary = Path(name).resolve()
                    try:
                        yield name
                    finally:
                        owned_temporary = previous
            def render(data, destination):
                destination = Path(destination).resolve()
                if png_enabled:
                    require(owned_temporary is not None and destination == owned_temporary,
                            "PNG normalization requires the verifier-owned temporary directory")
                    require(typed_equal(data, frozen_data), "Unbound PNG figure data")
                result = original_render(data, destination)
                if png_enabled:
                    pending = []
                    for name in PNG_NAMES:
                        saved, replay = regular(root / PACKAGE / name), regular(destination / name)
                        check = png_equivalence(saved, replay)
                        pending.append((name, saved, check))
                    # Both images must qualify before any temporary encoding is replaced.
                    for name, saved, check in pending:
                        if check["encoding_normalized"]:
                            (destination / name).write_bytes(saved)
                        report["png_replays"].append({"file": name, **check})
                return result
            analyze._repeat_portability = True
            analysis.analyze = analyze
            reporter.verify = verify
            publication.verify = verify_publication
            publication._render = render
            publication.TemporaryDirectory = temporary
            try:
                yield report
            finally:
                analysis.analyze = original
                reporter.verify = strict_verify
                publication.verify = strict_publication
                publication._render = original_render
                publication.TemporaryDirectory = original_temporary
                verify_inputs(root, evidence_path)
                png_observations(png_evidence_path)
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
