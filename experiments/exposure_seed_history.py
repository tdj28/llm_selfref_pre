"""Offline replay of one frozen freshness test, plus a fail-closed live seed guard."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FREEZE = "56b06eb6de7f09342c4d428bff3604c0ffba8e5a"
PRIOR = "0df8cc316b073fca463912ecabb61434511ad238"
REVIEW = "8fb86f7a3519bd845db18a163c9b4bda72fed363"
PRIOR_COUNT = 29
PRIOR_INVENTORY_SHA = "055fdadb035cc26b53400156f467f8b4596b0bc95319b721c049940fc122e0d5"
PLAN = "data/berg_dose_exposure/plan_20261004/PLAN.json"
PLAN_SHA = "3c0298e12cc9a9963061b0d74dc5e7f4e2e9a1122860684b1a063ad4080c3b37"
CONTINUATION_SHA = "4a327e25f3e24738670eda8c311ed9bd8e10bbbcaed36efb47d334a93399c032"
TEST_FILE = "tests/test_dose_exposure_protocol.py"
TEST_SHA = "ebef1409a0e7c318361f010217619474494399932463ca946fd7dcd21b2a2cfe"
TARGET = TEST_FILE + "::test_only_declared_design_fields_change_and_seeds_are_fresh"
ENFORCER = "tests/test_exposure_seed_history.py::test_historical_freshness_enforced"
MARKER = "EXPOSURE_SEED_HISTORY "
KNOWN = {
    PLAN: PLAN_SHA,
    "data/berg_dose_exposure/calibration_throughput_stop_v1_20261005/provenance/PLAN.json": PLAN_SHA,
    "data/berg_dose_exposure/calibration_throughput_stop_v1_20261005/raw/PLAN.json": PLAN_SHA,
    "data/berg_dose_exposure_continuation/fixed_main_v1_20261005/calibration/provenance/PLAN.json": PLAN_SHA,
    "data/berg_dose_exposure_continuation/fixed_main_v1_20261005/calibration/raw/PLAN.json": PLAN_SHA,
    "data/berg_dose_exposure_continuation/fixed_main_v1_20261005/main/PLAN.json": CONTINUATION_SHA,
    "data/berg_dose_exposure_continuation/fixed_main_v1_20261005/provenance/PLAN.json": CONTINUATION_SHA,
    "data/berg_dose_exposure_continuation/plan_v1_20261005/PLAN.json": CONTINUATION_SHA,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def relative(name):
    path = PurePosixPath(name)
    require(bool(name) and path.as_posix() == name and not path.is_absolute()
            and "\\" not in name and ":" not in name
            and all(p not in (".", "..") for p in path.parts), "Unsafe relative path")
    return name


def regular(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)) and path.is_file(),
            "Missing or nonregular input: " + path.name)
    return path.read_bytes()


def read_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def inventory(files):
    return [{"path": name, "sha256": sha(raw), "bytes": len(raw)}
            for name, raw in sorted(files.items())]


def clean_env():
    keep = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL",
            "TMP", "TEMP", "TMPDIR", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH")
    return {k: os.environ[k] for k in keep if k in os.environ}


class Git:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.env = {**clean_env(), "GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0",
                    "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0"}

    def query(self, *args, data=None):
        require(args[0] in ("ls-tree", "cat-file", "rev-list"), "Read-only local Git only")
        result = subprocess.run(["git", "--no-replace-objects", *args], cwd=self.root,
                                env=self.env, input=data, capture_output=True, timeout=60)
        require(result.returncode == 0, "Required local history unavailable; no fetch attempted")
        return result.stdout

    def tree(self, revision):
        result = {}
        for entry in self.query("ls-tree", "-rz", revision).split(b"\0"):
            if entry:
                header, name = entry.split(b"\t", 1)
                result[name.decode()] = tuple(header.decode().split())
        return result

    def read(self, tree, names):
        names = sorted(set(names))
        for name in names:
            relative(name)
            require(name in tree and tree[name][0] in ("100644", "100755")
                    and tree[name][1] == "blob", "Missing/nonregular historical blob: " + name)
        raw = self.query("cat-file", "--batch", data="".join(tree[n][2] + "\n" for n in names).encode())
        offset, result = 0, {}
        for name in names:
            end = raw.index(b"\n", offset)
            oid, kind, size = raw[offset:end].split()
            require(oid.decode() == tree[name][2] and kind == b"blob", "Unexpected Git blob")
            offset = end + 1
            result[name] = raw[offset:offset + int(size)]
            offset += int(size)
            require(raw[offset:offset + 1] == b"\n", "Truncated Git blob")
            offset += 1
        require(offset == len(raw), "Unexpected Git batch output")
        return result


def imports(name, raw, available):
    package, modules = name[:-3].split("/")[:-1], []
    for node in ast.walk(ast.parse(raw, filename=name)):
        if isinstance(node, ast.Import):
            modules.extend(a.name.split(".") for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[:len(package) - node.level + 1] if node.level else []
            base += node.module.split(".") if node.module else []
            modules.append(base)
            modules.extend(base + [a.name] for a in node.names if a.name != "*")
    found = set()
    for parts in modules:
        for i in range(1, len(parts) + 1):
            prefix = "/".join(parts[:i])
            found.update(n for n in (prefix + ".py", prefix + "/__init__.py") if n in available)
    return found


def seeds(value):
    result = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "seed" and type(item) is int:
                result.add(item)
            if key.endswith("seeds") and isinstance(item, list):
                result.update(n for n in item if type(n) is int)
            result.update(seeds(item))
    elif isinstance(value, list):
        for item in value:
            result.update(seeds(item))
    return result


def live_guard(root, prior, allowed, exposure_seeds):
    root = Path(root).resolve()
    data = root / "data"
    require(data.is_dir() and not data.is_symlink(), "Missing/nonregular live data root")
    live, overlaps = {}, {}
    for directory, dirs, names in os.walk(data, followlinks=False):
        require(not any((Path(directory) / n).is_symlink() for n in dirs), "Symlink in live plan corpus")
        if "PLAN.json" not in names:
            continue
        path = Path(directory) / "PLAN.json"
        name, raw = path.relative_to(root).as_posix(), regular(path)
        live[name] = raw
        if name in prior:
            require(raw == prior[name], "Historical plan drift: " + name)
        if name in allowed:
            require(raw == allowed[name], "Known plan drift: " + name)
        collision = exposure_seeds & seeds(read_json(raw))
        if collision:
            require(name in allowed, "Unknown colliding plan: " + name)
            overlaps[name] = len(collision)
    require(set(prior) <= set(live), "Historical plan missing from live corpus")
    require(PLAN in live, "Original exposure plan missing")
    return {"plans": len(live), "inventory_sha256": sha(encoded(inventory(live))),
            "known_overlaps": overlaps, "unknown_collisions": 0}


def snapshot(root):
    root, git = Path(root).resolve(), Git(root)
    lineage = git.query("rev-list", "--parents", "-n", "1", FREEZE).decode().split()
    require(lineage == [FREEZE, PRIOR], "Exposure freeze parent mismatch")
    old_tree, tree = git.tree(PRIOR), git.tree(FREEZE)
    prior_names = [n for n in old_tree if n.startswith("data/") and n.endswith("/PLAN.json")]
    prior = git.read(old_tree, prior_names)
    require(len(prior) == PRIOR_COUNT and sha(encoded(inventory(prior))) == PRIOR_INVENTORY_SHA,
            "Prior plan corpus inventory mismatch")
    plan_raw = git.read(tree, [PLAN])[PLAN]
    require(sha(plan_raw) == PLAN_SHA, "Exposure plan binding mismatch")
    plan = read_json(plan_raw)
    require(plan["source_hashes"].get(TEST_FILE) == TEST_SHA, "Frozen test binding mismatch")
    source, pending = {}, {TEST_FILE, "pytest.ini"}
    while pending:
        batch = git.read(tree, pending)
        for name, raw in batch.items():
            require(sha(raw) == plan["source_hashes"].get(name), "Unbound historical dependency: " + name)
            require(regular(root / name) == raw, "Executed source drift: " + name)
        source.update(batch)
        pending = set().union(*(imports(n, b, tree) for n, b in batch.items() if n.endswith(".py"))) - source.keys()
    allowed = git.read(git.tree(REVIEW), KNOWN)
    require(all(sha(raw) == KNOWN[n] for n, raw in allowed.items()), "Known plan binding mismatch")
    exposure_seeds = {row["seed"] for row in plan["rows"]}
    require(len(exposure_seeds) == 108, "Exposure seed inventory mismatch")
    require(not any(exposure_seeds & seeds(read_json(raw)) for raw in prior.values()),
            "Exposure seeds collide with historical plans")
    live = live_guard(root, prior, allowed, exposure_seeds)
    files = {**source, **prior}
    record = {"schema": "exposure-seed-history-v1", "source_freeze": FREEZE,
              "prior_commit": PRIOR, "prior_plan_count": len(prior),
              "prior_inventory_sha256": PRIOR_INVENTORY_SHA, "test_sha256": TEST_SHA,
              "target": TARGET, "files": inventory(files), "live_corpus": live}
    return files, record, prior, allowed, exposure_seeds


class Execution:
    def __init__(self):
        self.collected, self.passed, self.invalid = [], [], False

    def pytest_collection_finish(self, session):
        self.collected = [item.nodeid for item in session.items]

    def pytest_deselected(self, items):
        self.invalid |= bool(items)

    def pytest_runtest_logreport(self, report):
        self.invalid |= report.skipped or report.failed or hasattr(report, "wasxfail")
        if report.when == "call" and report.passed:
            self.passed.append(report.nodeid)

    def result(self, status):
        require(status == 0 and not self.invalid and self.collected == self.passed == [TARGET],
                "Frozen freshness node did not execute exactly once and pass")
        return {"target": TARGET, "collected": 1, "passed": 1}


def child():
    require(os.environ.get("EXPOSURE_HISTORY_CHILD") == "1", "Disposable child required")
    view = Path.cwd()
    record = read_json(regular(view / "_history.json"))
    for row in record["files"]:
        raw = regular(view / relative(row["path"]))
        require(len(raw) == row["bytes"] and sha(raw) == row["sha256"], "Historical view drift")
    actual_plans = {p.relative_to(view).as_posix() for p in (view / "data").rglob("PLAN.json")}
    expected_plans = {r["path"] for r in record["files"] if r["path"].endswith("/PLAN.json")}
    require(actual_plans == expected_plans and len(actual_plans) == record["prior_plan_count"],
            "Unexpected historical plan inventory")
    def offline(event, unused):
        if event in ("socket.connect", "socket.getaddrinfo", "socket.bind"):
            raise RuntimeError("Network forbidden in historical freshness replay")
    sys.addaudithook(offline)
    import pytest
    audit = Execution()
    status = pytest.main([TARGET, "-q", "-p", "no:cacheprovider", "--confcutdir", str(view)], plugins=[audit])
    print(MARKER + encoded(audit.result(status)).decode().strip())
    return 0


def replay(root=ROOT):
    files, record, prior, allowed, exposure_seeds = snapshot(root)
    with tempfile.TemporaryDirectory(prefix="exposure-seed-history-") as temporary:
        view = Path(temporary).resolve()
        for name, raw in {**files, "_history.json": encoded(record),
                          "_history_child.py": regular(Path(__file__))}.items():
            path = view / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        env = {**clean_env(), "HOME": str(view), "PYTHONPATH": str(view),
               "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
               "EXPOSURE_HISTORY_CHILD": "1"}
        result = subprocess.run([sys.executable, "-B", str(view / "_history_child.py"), "_child"],
                                cwd=view, env=env, capture_output=True, text=True, timeout=180)
        require(result.returncode == 0, "Historical freshness replay failed:\n" + result.stdout[-4000:] + result.stderr[-4000:])
        lines = [line[len(MARKER):] for line in result.stdout.splitlines() if line.startswith(MARKER)]
        require(len(lines) == 1, "Missing/duplicate historical execution receipt")
        execution = read_json(lines[0])
        require(execution == {"target": TARGET, "collected": 1, "passed": 1}, "Invalid execution receipt")
    require(live_guard(root, prior, allowed, exposure_seeds) == record["live_corpus"],
            "Live corpus changed during historical replay")
    require(all(regular(Path(root) / n) == b for n, b in files.items()), "Source/corpus changed during replay")
    return {k: v for k, v in record.items() if k != "files"} | {"execution": execution}


def collection_only(config):
    return getattr(getattr(config, "option", None), "collectonly", False)


def pytest_collection_finish(session):
    if collection_only(session.config) or os.environ.get("EXPOSURE_HISTORY_CHILD"):
        return
    if not any(i.nodeid == ENFORCER for i in session.items):
        return
    moved = [i for i in session.items if i.nodeid == TARGET]
    if moved:
        require(len(moved) == 1, "Duplicate freshness target collection")
        session.config._exposure_history_delegated = True
        session.items[:] = [i for i in session.items if i.nodeid != TARGET]
        session.testscollected = len(session.items)
        session.config.hook.pytest_deselected(items=moved)


def pytest_sessionfinish(session, exitstatus):
    if collection_only(session.config):
        return
    if getattr(session.config, "_exposure_history_delegated", False):
        if not successful_receipt(getattr(session.config, "_exposure_history_execution", None)):
            session.exitstatus = 1


def successful_receipt(result):
    return (isinstance(result, dict) and result.get("prior_plan_count") == PRIOR_COUNT
            and result.get("prior_commit") == PRIOR and result.get("source_freeze") == FREEZE
            and result.get("prior_inventory_sha256") == PRIOR_INVENTORY_SHA
            and result.get("test_sha256") == TEST_SHA
            and result.get("execution") == {"target": TARGET, "collected": 1, "passed": 1}
            and result.get("live_corpus", {}).get("unknown_collisions") == 0)


def pytest_terminal_summary(terminalreporter, config):
    if collection_only(config):
        return
    result = getattr(config, "_exposure_history_execution", None)
    if successful_receipt(result):
        terminalreporter.write_sep("-", "Exposure freshness: original node executed 1/1 and passed; "
                                  "29 pinned prior plans; live collision guard passed (no unknown reuse)")
    elif getattr(config, "_exposure_history_delegated", False):
        terminalreporter.write_sep("-", "Exposure freshness delegation FAILED: no successful execution receipt")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["_child"]:
        return child()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    print(MARKER + encoded(replay(args.root)).decode().strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
