"""Offline, evidence-bound reference Wilson quantile for one completed release.

Both original Linux failures remain archived. No numeric or image tolerance;
the unchanged release and paper verifiers must reconstruct all saved outputs.
"""
import argparse
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
from threading import RLock
from types import FunctionType

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "data/kolibri_swap/release_v1_20261005"
PACKAGE = "evidence/kolibri_extension"
MANIFEST_SHA = "78529659edb09af027e008e3d0513440933e8a560d4fe82c37718034e45e9ddf"
BINDING_SHA = "5f9e3d6eb923c02cb73d2a853ed778783c5988e0d05437f796b4fe65fb94adb8"
RELEASE_COMMIT = "3900a5ede5e6c003320960159e69811530f5346c"
REFERENCE_Z_HEX = "0x1.f5c0331eeff81p+0"
LINUX_Z_HEX = "0x1.f5c0331eeff82p+0"
EVIDENCE = ROOT / "provenance/kolibri_wilson/OBSERVATIONS.json"
HOSTED_EVIDENCE_SHA256 = "f0498cee648fb22116d6a8daf0c1512474130ce2fc403dd10b8ccbccc358ca70"
SCIENCE = {
    "experiments/openrouter_swap/analysis.py": "ce3f420ad33f561c17279fd624f41cf721ffbb93336448d86e375a234c7dd879",
    "experiments/kolibri_swap/analysis.py": "83cc6371d854bb6d260b19fe7e82824b5a2d660d521774cc5020b04720371f72",
}
ROW_SHA = {"screen": "4727deaac81f9882b9981f049963096a429fb8e2a2fd7469e04a5ef6e4997cf4",
           "main": "43e33f07a0360dde0987ef3b1ddccde9c24e467a514cdb7e7cd5e4bc20b2e7f9"}
ANALYSIS_SHA = {"screen": "94012eb4c9b287494432222833aec5e49ba3187e89e1ad1b109f4c76ffa17b71",
                "main": "b6c117df82b7b62bfe370188ecef2e245d8d21d1026470bfded203af23af3afc"}
QUALIFICATION_SHA = "e675ce9a3b9c7dbdb050b3ea4d861962d996871a4aae44c54013322f5c930c48"
_LOCK = RLock()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def value_sha(value):
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=True,
                          separators=(",", ":"), allow_nan=False).encode())


def regular(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)) and path.is_file(),
            "Missing/nonregular candidate input")
    return path.read_bytes()


def relative(name):
    require(type(name) is str and name, "Unsafe candidate input path")
    path = Path(name)
    require(not path.is_absolute() and path.as_posix() == name and ".." not in path.parts
            and "\\" not in name and ":" not in name, "Unsafe candidate input path")
    return path


def _inventory(root, entries, extra):
    names = set(extra)
    for entry in entries:
        name = entry["path"]
        require(name not in names, "Duplicate candidate inventory entry")
        raw = regular(root / relative(name))
        require(len(raw) == entry["bytes"] and sha(raw) == entry["sha256"], "Bound artifact changed")
        names.add(name)
    actual = set()
    for path in root.rglob("*"):
        require(not path.is_symlink() and (path.is_dir() or path.is_file()), "Nonregular candidate inventory")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    require(actual == names, "Bound artifact inventory changed")


def verify_inputs(root):
    root = Path(root).resolve()
    raw = regular(root / RELEASE / "MANIFEST.json")
    require(sha(raw) == MANIFEST_SHA, "Release manifest anchor changed")
    _inventory(root / RELEASE, json.loads(raw)["files"], {"MANIFEST.json"})
    raw = regular(root / PACKAGE / "BINDING.json")
    require(sha(raw) == BINDING_SHA, "Paper binding anchor changed")
    binding = json.loads(raw)
    require(binding["release_manifest_sha256"] == MANIFEST_SHA
            and binding["source_commit"] == RELEASE_COMMIT, "Paper release pin changed")
    _inventory(root / PACKAGE, binding["outputs"], {"BINDING.json"})
    exporter = json.loads(regular(root / RELEASE / "EXPORTER.json"))
    hashes = {}
    for sources in (SCIENCE, exporter["source_hashes"], binding["source_hashes"]):
        for name, expected in sources.items():
            require(name not in hashes or hashes[name] == expected, "Conflicting candidate source binding")
            require(sha(regular(root / relative(name))) == expected, "Bound scientific/reporting source changed")
            hashes[name] = expected
    for phase in ROW_SHA:
        require(value_sha(json.loads(regular(root / RELEASE / (phase + "_rows.json")))) == ROW_SHA[phase]
                and value_sha(json.loads(regular(root / RELEASE / (phase + "_analysis.json")))) == ANALYSIS_SHA[phase],
                "Whole row/analysis anchor changed")
    require(value_sha(json.loads(regular(root / RELEASE / "qualification.json"))) == QUALIFICATION_SHA,
            "Qualification anchor changed")
    return hashes


def reference_wilson(original, z_hex=REFERENCE_Z_HEX):
    """Execute unchanged frozen bytecode with only its NormalDist dependency replaced."""
    class ReferenceNormal:
        def inv_cdf(self, probability):
            require(type(probability) is float and probability.hex() == (0.975).hex(),
                    "Unexpected Wilson probability")
            return float.fromhex(z_hex)
    require(z_hex in (REFERENCE_Z_HEX, LINUX_Z_HEX), "Unmeasured Wilson reference")
    return FunctionType(original.__code__, {**original.__globals__, "NormalDist": ReferenceNormal},
                        original.__name__, original.__defaults__, original.__closure__)


def observations(path=EVIDENCE):
    raw = regular(path)
    require(sha(raw) == HOSTED_EVIDENCE_SHA256, "Hosted observation provenance changed")
    evidence = json.loads(raw)
    reports = []
    for item in evidence["observations"]:
        raw = regular(Path(path).parent / relative(item["diagnostic_path"]))
        require(sha(raw) == item["diagnostic_sha256"], "Hosted diagnostic bytes changed")
        report = json.loads(raw)
        require(report["python"] == item["python"] and report["system"] == "Linux"
                and report["machine"] == "x86_64" and report["normal_dist_z_hex"] == LINUX_Z_HEX
                and report["normal_dist_z"].hex() == LINUX_Z_HEX
                and report["manifest_sha256"] == MANIFEST_SHA
                and report["exact_replay"] is False and report["frozen_derived_comparison_equal"] is False,
                "Hosted runtime or failure observation changed")
        require(value_sha(report["files"]) == evidence["files_canonical_sha256"]
                and value_sha(report["differences"]) == evidence["differences_canonical_sha256"]
                and report["difference_count"] == len(report["differences"]) == 623,
                "Entire hosted file/difference inventory changed")
        reports.append(report)
    require(len(reports) == 2 and [r["python"] for r in reports] == ["3.10.21", "3.12.14"],
            "Both measured hosted Python versions required")
    require(all(reports[0][key] == reports[1][key]
                for key in ("files", "differences", "summary", "exporter_source_hashes")),
            "Hosted observations disagree")
    return evidence, reports[0]


def validate_observed_outputs(root, report, common):
    """Reconstruct every measured output from Wilson endpoints and the frozen table hash."""
    replay = {}
    for name, item in report["files"].items():
        raw = regular(root / RELEASE / relative(name))
        value = json.loads(raw)
        require(sha(raw) == item["saved_file_sha256"] and value_sha(value) == item["saved_canonical_sha256"],
                "Observed saved-output anchor changed")
        replay[name] = deepcopy(value)
    linux_wilson = reference_wilson(common._wilson, LINUX_Z_HEX)
    floats, hashes = 0, 0
    for row in report["differences"]:
        if row["kind"] == "str":
            require(row["file"] == "FIGURES.json" and row["path"] == "/source_tables_canonical_sha256",
                    "Unmeasured non-Wilson difference")
            hashes += 1
            continue
        require(row["kind"] == row["saved_type"] == row["replay_type"] == "float"
                and row["path"].endswith(("/wilson_95/0", "/wilson_95/1")),
                "Unmeasured difference path/type")
        parent = replay[row["file"]]
        for part in row["path"].split("/")[1:-2]:
            part = part.replace("~1", "/").replace("~0", "~")
            parent = parent[int(part)] if type(parent) is list else parent[part]
        index = int(row["path"][-1])
        require(parent["wilson_95"][index].hex() == row["saved_hex"]
                and row["saved"].hex() == row["saved_hex"] and row["replay"].hex() == row["replay_hex"],
                "Measured Wilson scalar changed")
        actual = linux_wilson(parent["positive"], parent["observed"])[index]
        require(actual.hex() == row["replay_hex"], "Observed value is not the frozen Wilson formula")
        parent["wilson_95"][index] = actual
        floats += 1
    require((floats, hashes) == (622, 1), "Observed Wilson difference inventory changed")
    reporter = importlib.import_module("experiments.kolibri_release")
    require(Path(reporter.__file__).resolve() == root / "experiments/kolibri_release.py", "Foreign reporter")
    derived = {name: replay[name] for name in reporter.JSON_OUTPUTS}
    images = {name: regular(root / RELEASE / name) for name in ("figures/cells.png", "figures/primary.png")}
    replay["FIGURES.json"] = reporter.figure_receipts(derived, images)
    require(all(value_sha(value) == report["files"][name]["replay_canonical_sha256"]
                for name, value in replay.items()), "Whole measured replay output does not reconstruct")
    require(sha(reporter.summary(derived)) == report["summary"]["saved_sha256"]
            == report["summary"]["replay_sha256"] and report["summary"]["exact"] is True,
            "Measured summary differs")


@contextmanager
def source_imports(root):
    previous = sys.path[:]
    sys.path.insert(0, str(root))
    try:
        yield
    finally:
        sys.path[:] = previous


@contextmanager
def reference_replay(root=ROOT):
    """Keep the reference limited to exact completed Kolibri rows and whole outputs."""
    root = Path(root).resolve()
    with _LOCK, source_imports(root):
        sources = verify_inputs(root)
        evidence, observed = observations()
        common = importlib.import_module("experiments.openrouter_swap.analysis")
        analysis = importlib.import_module("experiments.kolibri_swap.analysis")
        for module, name in ((common, "experiments/openrouter_swap/analysis.py"),
                             (analysis, "experiments/kolibri_swap/analysis.py")):
            require(Path(module.__file__).resolve() == root / name, "Analysis imported from another checkout")
        original_wilson, original_analyze, original_qualify = common._wilson, analysis.analyze, analysis.qualify
        require(not getattr(original_wilson, "_kolibri_reference", False), "Nested Wilson candidate context")
        native = common.NormalDist().inv_cdf(0.975)
        require(type(native) is float and native.hex() in (REFERENCE_Z_HEX, LINUX_Z_HEX),
                "Unmeasured native Wilson quantile")
        validate_observed_outputs(root, observed, common)
        frozen_wilson = reference_wilson(original_wilson)
        active = ContextVar("kolibri_reference_wilson", default=False)
        report = {"policy": "exact archived observations and whole outputs; reference Wilson z only",
                  "hosted_evidence_sha256": HOSTED_EVIDENCE_SHA256,
                  "original_hosted_exact_replay": "FAIL", "original_failure": evidence["original_strict_failure"],
                  "native_z_hex": native.hex(), "reference_z_hex": REFERENCE_Z_HEX,
                  "manifest_sha256": MANIFEST_SHA, "binding_sha256": BINDING_SHA,
                  "source_hashes": sources, "analysis_replays": [], "qualification_replays": 0}
        def wilson(positive, n):
            return frozen_wilson(positive, n) if active.get() else original_wilson(positive, n)
        def analyze(rows, phase):
            require(phase in ROW_SHA and type(rows) is list and value_sha(rows) == ROW_SHA[phase],
                    "Unbound Kolibri analysis rows")
            token = active.set(True)
            try:
                result = original_analyze(rows, phase)
            finally:
                active.reset(token)
            require(value_sha(result) == ANALYSIS_SHA[phase], "Unknown whole-analysis replay variation")
            report["analysis_replays"].append(phase)
            return result
        def qualify(rows):
            require(type(rows) is list and value_sha(rows) == ROW_SHA["screen"], "Unbound Kolibri qualification rows")
            token = active.set(True)
            try:
                result = original_qualify(rows)
            finally:
                active.reset(token)
            require(value_sha(result) == QUALIFICATION_SHA, "Unknown qualification replay variation")
            report["qualification_replays"] += 1
            return result
        wilson._kolibri_reference = True
        common._wilson, analysis.analyze, analysis.qualify = wilson, analyze, qualify
        try:
            yield report
        finally:
            common._wilson, analysis.analyze, analysis.qualify = original_wilson, original_analyze, original_qualify
            verify_inputs(root)
            observations()


def verify(root=ROOT):
    root = Path(root).resolve()
    with reference_replay(root) as report:
        binder = importlib.import_module("scripts.verify_kolibri_extension")
        require(Path(binder.__file__).resolve() == root / "scripts/verify_kolibri_extension.py", "Foreign paper binder")
        result = binder.verify_package(root / PACKAGE, root / RELEASE, MANIFEST_SHA, RELEASE_COMMIT,
                                       repo=root, expected_binding_sha256=BINDING_SHA)
        require(report["analysis_replays"] == ["screen", "main", "screen", "main"],
                "Both original release and paper analysis replays are required")
    return {"paper_verification": result, "kolibri_wilson_portability": report}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    def offline(event, arguments):
        if event in ("socket.connect", "socket.getaddrinfo", "socket.bind"):
            raise RuntimeError("Network forbidden in Wilson reporting verification")
    sys.addaudithook(offline)
    print(json.dumps(verify(args.root), sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
