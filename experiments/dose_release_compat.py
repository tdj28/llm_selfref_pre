"""Offline historical-source view for post-outcome dose reporting, never execution."""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import runpy
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FREEZE = "686efa2491a2334fcd2aff835627b24346d1dbb4"
PLAN = "data/berg_dose_exposure_continuation/plan_v1_20261005/PLAN.json"
PLAN_SHA = "4a327e25f3e24738670eda8c311ed9bd8e10bbbcaed36efb47d334a93399c032"
AUDITOR = "scripts/audit_public_release.py"
OLD_AUDITOR = "82900a8b6715cf9c8d7fd2a0eaf886ceae800c5d7e46949c60b39c17ff829db6"
NEW_AUDITOR = "97db36ab3d45eb9e59127b66ee96fce57897dc27aa5ce2349b60538171d5a1e6"
REPORTERS = ("experiments/dose_main_release.py", "tests/test_dose_main_release.py",
             "experiments/dose_release_compat.py", "tests/test_dose_release_compat.py")
ANCESTOR_PLANS = ("data/berg_dose_ladder/plan_20261004/PLAN.json",
                  "data/berg_dose_window/plan_20261004/PLAN.json")
SUITES = ("tests/test_exposure_continuation.py", "tests/test_dose_main_release.py",
          "tests/test_dose_window_protocol.py::test_all_111_old_frozen_sources_remain_exact",
          "tests/test_dose_exposure_protocol.py::test_all_122_old_frozen_sources_remain_exact",
          "tests/test_mapping_scaled_release.py::test_sidecar_does_not_change_frozen_source_closure")
ENFORCER = "tests/test_dose_release_compat.py::test_historical_suites_enforced"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def relative(name):
    require(isinstance(name, str) and bool(name), "Unsafe relative source path")
    path = PurePosixPath(name)
    require(path.as_posix() == name
            and not path.is_absolute() and "\\" not in name and ":" not in name
            and all(p not in (".", "..") for p in path.parts), "Unsafe relative source path")
    return path


def regular(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink in reporting input")
    require(path.is_file(), "Missing regular reporting input")
    return path.read_bytes()


def clean_env():
    # Neither credentials nor ambient Git/Python overrides enter the child.
    keep = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL",
            "TMP", "TEMP", "TMPDIR", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH")
    return {k: os.environ[k] for k in keep if k in os.environ}


class GitBlobs:
    def __init__(self, root):
        self.root = Path(root).resolve()
        env = {**clean_env(), "GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0",
               "GIT_TERMINAL_PROMPT": "0", "GIT_NO_REPLACE_OBJECTS": "1"}
        result = subprocess.run(["git", "-C", str(self.root), "rev-parse", "--absolute-git-dir"],
                                env=env, capture_output=True, check=True)
        self.env = {**env, "GIT_DIR": result.stdout.decode().strip(), "GIT_WORK_TREE": str(self.root)}
        self.tree = {}
        for entry in self.query("ls-tree", "-rz", FREEZE).split(b"\0"):
            if entry:
                header, name = entry.split(b"\t", 1)
                mode, kind, oid = header.decode().split()
                self.tree[name.decode()] = (mode, kind, oid)

    def query(self, *args, data=None):
        require(args[0] in ("ls-tree", "cat-file", "rev-parse"), "Read-only Git queries only")
        result = subprocess.run(["git", "--no-replace-objects", *args], cwd=self.root,
                                env=self.env, input=data, capture_output=True)
        require(result.returncode == 0, "Required local frozen Git objects unavailable; no fetch attempted")
        return result.stdout

    def read(self, names):
        names = sorted(set(names))
        for name in names:
            relative(name)
            entry = self.tree.get(name)
            require(entry is not None and entry[0] in ("100644", "100755") and entry[1] == "blob",
                    "Missing/nonregular frozen blob: " + name)
        raw = self.query("cat-file", "--batch", data="".join(self.tree[n][2] + "\n" for n in names).encode())
        offset, result = 0, {}
        for name in names:
            end = raw.index(b"\n", offset)
            oid, kind, size = raw[offset:end].split()
            require(oid.decode() == self.tree[name][2] and kind == b"blob", "Unexpected Git object")
            offset, size = end + 1, int(size)
            result[name] = raw[offset:offset + size]
            offset += size
            require(raw[offset:offset + 1] == b"\n", "Truncated Git blob")
            offset += 1
        require(offset == len(raw), "Unexpected Git batch output")
        return result

    def source_paths(self):
        code = ("import json; from experiments.berg_dose_exposure_continuation import protocol as p; "
                "print(json.dumps(p.source_paths()))")
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=self.root,
                                env={**self.env, "PYTHONPATH": str(self.root)},
                                capture_output=True, text=True, timeout=120)
        require(result.returncode == 0, "Cannot reconstruct current scientific source inventory")
        return json.loads(result.stdout)


def imports(name, raw, available):
    """Include local Python dependencies and package initializers, not whole history."""
    if not name.endswith(".py"):
        return set()
    package = name[:-3].split("/")[:-1]
    modules = []
    for node in ast.walk(ast.parse(raw, filename=name)):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[:len(package) - node.level + 1] if node.level else []
            base += node.module.split(".") if node.module else []
            modules.append(".".join(base))
            modules.extend(".".join([*base, a.name]) for a in node.names if a.name != "*")
    result = set()
    for module in modules:
        parts = module.split(".")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            for candidate in (prefix + ".py", prefix + "/__init__.py"):
                if candidate in available:
                    result.add(candidate)
    return result


def snapshot(root):
    root = Path(root).resolve()
    git = GitBlobs(root)
    plan_raw = git.read([PLAN])[PLAN]
    require(digest(plan_raw) == PLAN_SHA and regular(root / PLAN) == plan_raw, "Frozen continuation plan drift")
    plan = json.loads(plan_raw)
    bindings = {**plan["source_hashes"], **plan["input_hashes"], PLAN: PLAN_SHA}
    require(plan["source_hashes"][AUDITOR] == OLD_AUDITOR, "Unexpected historical public auditor")
    prefix = plan["continuation"]["release"]
    manifest_name = prefix + "/MANIFEST.json"
    manifest_raw = git.read([manifest_name])[manifest_name]
    require(digest(manifest_raw) == plan["continuation"]["manifest_sha256"], "Calibration manifest drift")
    for row in json.loads(manifest_raw)["files"]:
        name = prefix + "/" + str(relative(row["path"]))
        require(name not in bindings or bindings[name] == row["sha256"], "Conflicting calibration binding")
        bindings[name] = row["sha256"]
    for name, raw in git.read(ANCESTOR_PLANS).items():
        require(name not in bindings or bindings[name] == digest(raw), "Conflicting ancestor plan binding")
        bindings[name] = digest(raw)
    files = git.read(bindings)
    for name, expected in bindings.items():
        require(digest(files[name]) == expected, "Frozen blob hash mismatch: " + name)
        current = regular(root / name)
        if name == AUDITOR:
            require(digest(current) in (OLD_AUDITOR, NEW_AUDITOR), "Unapproved current public auditor")
            current_auditor = current
        else:
            require(current == files[name], "Scientific source/input drift: " + name)
    for name in REPORTERS:
        require(name not in bindings, "Reporting adapter entered frozen closure")
        files[name] = regular(root / name)
    checked = set()
    while True:
        needed = set()
        for name in set(files) - checked:
            needed.update(imports(name, files[name], git.tree))
            checked.add(name)
        needed -= files.keys()
        if not needed:
            break
        for name, raw in git.read(needed).items():
            require(regular(root / name) == raw, "Historical reporting dependency drift: " + name)
            files[name] = raw
    require(set(git.source_paths()) == set(plan["source_hashes"]), "Scientific source inventory drift")
    # No unbound extra artifact can be hidden by materializing only the manifest.
    current_prefix = set()
    for path in (root / prefix).rglob("*"):
        require(not path.is_symlink(), "Calibration artifact symlink")
        if path.is_file():
            current_prefix.add(path.relative_to(root).as_posix())
        else:
            require(path.is_dir(), "Nonregular calibration artifact")
    require(current_prefix == {n for n in bindings if n.startswith(prefix + "/")}, "Calibration inventory drift")
    record = {"schema": "dose-release-compat-v1", "scientific_freeze": FREEZE, "plan_sha256": PLAN_SHA,
              "historical_public_auditor_sha256": OLD_AUDITOR,
              "current_public_auditor_sha256": digest(current_auditor),
              "reporting_source_hashes": {n: digest(files[n]) for n in REPORTERS},
              "historical_view_sha256": digest(encoded({n: digest(b) for n, b in sorted(files.items())})),
              "compatibility_scope": "Offline reporting/tests only; exact auditor exception; unchanged scientific sources and prefix"}
    return git, files, current_auditor, record


@contextmanager
def historical_view(root=ROOT):
    git, files, scanner, record = snapshot(root)
    with tempfile.TemporaryDirectory(prefix="dose-reporting-") as temporary:
        view = Path(temporary).resolve()
        for name, raw in {**files, "_compat/current_auditor.py": scanner,
                          "_compat/record.json": encoded(record)}.items():
            path = view / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        env = {**git.env, "GIT_WORK_TREE": str(view), "HOME": str(view),
               "PYTHONPATH": str(view), "PYTHONDONTWRITEBYTECODE": "1",
               "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "MPLCONFIGDIR": str(view / "_compat/mpl"),
               "DOSE_COMPAT_CHILD": "1"}
        yield view, env, record


class HistoricalTests:
    def __init__(self):
        self.collected, self.passed, self.deselected = [], [], []
        self.incomplete = False

    def pytest_collection_finish(self, session):
        self.collected = [item.nodeid for item in session.items]

    def pytest_deselected(self, items):
        self.deselected.extend(item.nodeid for item in items)

    def pytest_runtest_logreport(self, report):
        self.incomplete |= report.skipped or report.failed
        if report.when == "call" and report.passed:
            self.passed.append(report.nodeid)

    def result(self, status):
        require(status == 0 and self.collected and not self.incomplete and not self.deselected
                and sorted(self.collected) == sorted(self.passed), "Incomplete historical test execution")
        for target in SUITES:
            require(any(n == target or n.startswith(target + "::") for n in self.collected),
                    "Historical test target did not execute: " + target)
        return {"requested": list(SUITES), "collected": len(self.collected), "passed": len(self.passed)}


def child(action, arguments):
    require(os.environ.get("DOSE_COMPAT_CHILD") == "1", "Historical child required")
    record = json.loads((ROOT / "_compat/record.json").read_bytes())
    scanner_path = ROOT / "_compat/current_auditor.py"
    require(digest(scanner_path.read_bytes()) == record["current_public_auditor_sha256"], "Scanner copy drift")
    def offline(event, args):
        if event in ("socket.connect", "socket.getaddrinfo", "socket.bind"):
            raise RuntimeError("Network is forbidden in historical reporting")
    sys.addaudithook(offline)
    # Only this disposable process resolves scanner imports to the current code.
    # The historical file remains byte-exact for all frozen source checks.
    spec = importlib.util.spec_from_file_location("scripts.audit_public_release", scanner_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if action == "test-frozen":
        require(not arguments, "Historical suites cannot be filtered")
        import pytest
        audit = HistoricalTests()
        status = pytest.main([*SUITES, "-q", "-p", "no:cacheprovider"], plugins=[audit])
        print("DOSE_HISTORICAL_TESTS " + encoded(audit.result(status)).decode().strip())
        return 0
    require(action in ("build", "verify"), "Reporting action only")
    sys.argv = ["dose_main_release", action, *arguments]
    runpy.run_module("experiments.dose_main_release", run_name="__main__")
    return 0


def run_child(view, env, action, arguments=()):
    result = subprocess.run([sys.executable, "-B", "-m", "experiments.dose_release_compat",
                             "_child", action, *map(str, arguments)], cwd=view, env=env,
                            capture_output=True, text=True, timeout=1800)
    require(result.returncode == 0, "Historical reporting failed:\n" + result.stdout[-6000:] + result.stderr[-6000:])
    return result.stdout


def test_frozen(root=ROOT):
    with historical_view(root) as (view, env, _):
        return run_child(view, env, "test-frozen")


def public_record(record, manifest):
    return {**record, "release_manifest_sha256": digest(regular(manifest))}


def report(action, arguments, destination, root=ROOT):
    destination = Path(destination).absolute()
    sidecar = destination.with_name(destination.name + ".compat.json")
    require(not any(p.is_symlink() for p in (destination, sidecar, *destination.parents)), "Symlink in release path")
    if action == "build":
        require(not sidecar.exists(), "Compatibility receipt already exists")
    with historical_view(root) as (view, env, record):
        if action == "verify":
            require(json.loads(regular(sidecar)) == public_record(record, destination / "MANIFEST.json"),
                    "Compatibility receipt or release manifest drift")
        output = run_child(view, env, action, arguments)
        require(snapshot(root)[3] == record, "Reporting sources changed during export")
        if action == "build":
            with sidecar.open("xb") as handle:
                handle.write(encoded(public_record(record, destination / "MANIFEST.json")))
    return output


def pytest_collection_finish(session):
    """Root CI delegates exact suites only when their enforcing test will run."""
    if os.environ.get("DOSE_COMPAT_CHILD") or not any(i.nodeid == ENFORCER for i in session.items):
        return
    session.config._dose_delegation_selected = True
    moved = [i for i in session.items if i.nodeid in SUITES or i.nodeid.split("::", 1)[0] in SUITES]
    session.items[:] = [i for i in session.items if i not in moved]
    session.testscollected = len(session.items)
    if moved:
        session.config.hook.pytest_deselected(items=moved)


def pytest_terminal_summary(terminalreporter, config):
    if getattr(config, "_dose_delegation_selected", False):
        result = getattr(config, "_dose_historical_execution", None)
        message = (f"Historical dose delegation: {result['passed']}/{result['collected']} tests executed "
                   "in the verified source view with the current public scanner"
                   if result else "Historical dose delegation did not complete; enforcing test must pass")
        terminalreporter.write_sep("-", message)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "_child":
        return child(argv[1], argv[2:])
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("test-frozen")
    build = sub.add_parser("build")
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--destination", type=Path, required=True)
    build.add_argument("--mode", choices=("completed", "partial_technical_failure"), required=True)
    build.add_argument("--controller-ledger", type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--manifest-sha256")
    verify.add_argument("--controller-receipt", type=Path)
    verify.add_argument("--controller-ledger", type=Path)
    args = parser.parse_args(argv)
    if args.action == "test-frozen":
        print(test_frozen(), end="")
    else:
        arguments = []
        for name, value in vars(args).items():
            if name != "action" and value is not None:
                arguments.extend(["--" + name.replace("_", "-"), str(value.absolute() if isinstance(value, Path) else value)])
        destination = args.destination if args.action == "build" else args.root
        print(report(args.action, arguments, destination), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
