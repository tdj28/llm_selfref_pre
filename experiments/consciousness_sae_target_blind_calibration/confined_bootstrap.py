#!/usr/bin/env python3
"""Hash-bound, stdlib-only bootstrap for confined audit recovery children.

This file is executed directly, never with ``-m``.  Its required startup form
is ``python -B -E -s -S /absolute/path/to/confined_bootstrap.py``.  It validates
the complete inventory of every Python import root, replaces ``sys.path`` with
only those roots, installs process-lifetime import/model guards, and only then
imports the recovery module and dispatches the selected confined operation.

The root manifest is deliberately external to all inventoried roots so its
physical SHA-256 can be bound in the authorized child argv without creating a
self-referential active-root inventory.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.machinery
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
MANIFEST_STATUS = "approved_exact_python_import_roots"
BOOTSTRAP_RELATIVE_PATH = (
    "experiments/consciousness_sae_target_blind_calibration/confined_bootstrap.py"
)
RECOVERY_MODULE = (
    "experiments.consciousness_sae_target_blind_calibration.audit_recovery"
)
STATE_MODULE = "_consciousness_sae_confined_bootstrap_state"
MODES = ("preflight-child", "execute-confined")

_HEX64 = re.compile(r"[0-9a-f]{64}")
_ROOT_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)

_FORBIDDEN_STARTUP_ENVIRONMENT = (
    "LD_AUDIT",
    "LD_PRELOAD",
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONPATH",
    "PYTHONPLATLIBDIR",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
)
_FORBIDDEN_PREIMPORT_ROOTS = frozenset(
    {"experiments", "numpy", "safetensors", "torch", "transformers"}
)
_FORBIDDEN_MODULES = frozenset(
    {
        "experiments.consciousness_sae_realization_validation.runtime",
        "experiments.consciousness_sae_realization_validation.guest_launcher",
        "experiments.consciousness_sae_realization_validation.runpod_orchestrator",
        "experiments.consciousness_sae_target_blind_calibration.runner",
        "experiments.consciousness_sae_target_blind_calibration.guest_launcher",
    }
)
_FORBIDDEN_STARTUP_MODULES = frozenset({"site", "sitecustomize", "usercustomize"})
_GUARDED_LOADER_MODULES = frozenset(
    {
        "torch.nn.modules.module",
        "transformers.modeling_utils",
        "transformers.models.auto.auto_factory",
    }
)

_FILE_FIELDS = frozenset({"path", "bytes", "sha256"})
_EXECUTABLE_FIELDS = frozenset({"path", "bytes", "sha256"})
_ROOT_FIELDS = frozenset(
    {
        "name",
        "role",
        "path",
        "files",
        "directories",
        "file_count",
        "directory_count",
        "total_bytes",
        "file_inventory_sha256",
        "directory_inventory_sha256",
        "inventory_sha256",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "python_executable",
        "bootstrap_relative_path",
        "bootstrap_sha256",
        "active_root",
        "roots",
        "sys_path",
        "roots_inventory_sha256",
        "receipt_sha256",
    }
)


class ConfinedBootstrapError(RuntimeError):
    """The confined import closure or process-lifetime guard failed closed."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ConfinedBootstrapError("value is not canonical JSON") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_hex64(value: Any, label: str) -> str:
    normalized = str(value)
    if _HEX64.fullmatch(normalized) is None:
        raise ConfinedBootstrapError(f"{label} is not a lowercase SHA-256")
    return normalized


def _canonical_existing(path: Path, label: str) -> Path:
    lexical = Path(os.path.abspath(path.expanduser()))
    try:
        resolved = lexical.resolve(strict=True)
        details = lexical.lstat()
    except OSError as exc:
        raise ConfinedBootstrapError(f"{label} is missing") from exc
    if lexical != resolved or stat.S_ISLNK(details.st_mode):
        raise ConfinedBootstrapError(f"{label} is not canonical and symlink-free")
    return resolved


def _canonical_directory(path: Path, label: str) -> Path:
    resolved = _canonical_existing(path, label)
    try:
        mode = resolved.stat().st_mode
    except OSError as exc:
        raise ConfinedBootstrapError(f"{label} is unreadable") from exc
    if not stat.S_ISDIR(mode):
        raise ConfinedBootstrapError(f"{label} is not a directory")
    return resolved


def _canonical_regular_file(path: Path, label: str) -> Path:
    resolved = _canonical_existing(path, label)
    try:
        details = resolved.stat()
    except OSError as exc:
        raise ConfinedBootstrapError(f"{label} is unreadable") from exc
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise ConfinedBootstrapError(f"{label} is not a uniquely linked regular file")
    return resolved


def _stable_file_record(path: Path, relative: str | None = None) -> dict[str, Any]:
    flags = os.O_RDONLY | _O_CLOEXEC | _O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ConfinedBootstrapError(
                f"inventory file is not a uniquely linked regular file: {path}"
            )
        digest = hashlib.sha256()
        observed_bytes = 0
        while block := os.read(descriptor, 8 * 1024 * 1024):
            digest.update(block)
            observed_bytes += len(block)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise ConfinedBootstrapError(f"could not hash inventory file: {path}") from exc
    finally:
        if "descriptor" in locals():
            os.close(descriptor)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_before != identity_after or observed_bytes != before.st_size:
        raise ConfinedBootstrapError(f"inventory file changed while hashing: {path}")
    return {
        "path": path.as_posix() if relative is None else relative,
        "bytes": observed_bytes,
        "sha256": digest.hexdigest(),
    }


def _relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfinedBootstrapError(f"{label} is not a relative POSIX path")
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or parsed.as_posix() != value
        or any(part in ("", ".", "..") for part in parsed.parts)
    ):
        raise ConfinedBootstrapError(f"{label} is not a canonical relative path")
    return value


def inventory_root(name: str, role: str, root: Path) -> dict[str, Any]:
    """Build the exact manifest record for one import root.

    This helper is for the trusted staging step.  The confined path independently
    rebuilds and compares the same record before changing ``sys.path``.
    """

    if _ROOT_NAME.fullmatch(name) is None:
        raise ConfinedBootstrapError("import-root name is invalid")
    if role not in ("active", "dependency"):
        raise ConfinedBootstrapError("import-root role is invalid")
    canonical = _canonical_directory(root, f"{name} import root")
    files: list[dict[str, Any]] = []
    directories: list[str] = []
    seen_files: set[tuple[int, int]] = set()
    try:
        candidates = sorted(canonical.rglob("*"), key=lambda item: item.as_posix())
    except OSError as exc:
        raise ConfinedBootstrapError(
            f"could not traverse import root: {canonical}"
        ) from exc
    for path in candidates:
        try:
            details = path.lstat()
        except OSError as exc:
            raise ConfinedBootstrapError(
                f"could not stat import-root entry: {path}"
            ) from exc
        relative = path.relative_to(canonical).as_posix()
        _relative_path(relative, "import-root entry")
        if stat.S_ISLNK(details.st_mode):
            raise ConfinedBootstrapError(f"import root contains a symlink: {relative}")
        if stat.S_ISDIR(details.st_mode):
            directories.append(relative)
            continue
        if not stat.S_ISREG(details.st_mode):
            raise ConfinedBootstrapError(
                f"import root contains a special file: {relative}"
            )
        identity = (int(details.st_dev), int(details.st_ino))
        if details.st_nlink != 1 or identity in seen_files:
            raise ConfinedBootstrapError(
                f"import root contains a hard-linked file: {relative}"
            )
        seen_files.add(identity)
        files.append(_stable_file_record(path, relative))
    directories.sort()
    files.sort(key=lambda row: str(row["path"]))
    file_hash = canonical_sha256(files)
    directory_hash = canonical_sha256(directories)
    core = {
        "name": name,
        "role": role,
        "path": canonical.as_posix(),
        "files": files,
        "directories": directories,
        "file_count": len(files),
        "directory_count": len(directories),
        "total_bytes": sum(int(row["bytes"]) for row in files),
        "file_inventory_sha256": file_hash,
        "directory_inventory_sha256": directory_hash,
    }
    return {**core, "inventory_sha256": canonical_sha256(core)}


def build_roots_manifest(
    *,
    python_executable: Path,
    active_root: Path,
    dependency_roots: Sequence[tuple[str, Path]],
    sys_path: Sequence[Path] | None = None,
) -> dict[str, Any]:
    """Build a staging manifest consumed by both confined child modes."""

    executable = _canonical_regular_file(python_executable, "Python executable")
    active = _canonical_directory(active_root, "active root")
    if not dependency_roots:
        raise ConfinedBootstrapError("at least one dependency root is required")
    roots = [inventory_root("active_root", "active", active)]
    names = {"active_root"}
    for name, root in dependency_roots:
        if name in names:
            raise ConfinedBootstrapError("import-root name is duplicated")
        names.add(name)
        roots.append(inventory_root(name, "dependency", root))
    paths = [str(row["path"]) for row in roots]
    if len(paths) != len(set(paths)):
        raise ConfinedBootstrapError("import-root path is duplicated")
    approved_sys_path = (
        paths
        if sys_path is None
        else [
            _canonical_directory(path, "approved sys.path root").as_posix()
            for path in sys_path
        ]
    )
    if (
        not approved_sys_path
        or approved_sys_path[0] != active.as_posix()
        or len(approved_sys_path) != len(set(approved_sys_path))
        or any(
            not any(
                candidate == Path(root_path) or Path(root_path) in candidate.parents
                for root_path in paths
            )
            for candidate in map(Path, approved_sys_path)
        )
    ):
        raise ConfinedBootstrapError("approved sys.path is outside inventoried roots")
    bootstrap = active / BOOTSTRAP_RELATIVE_PATH
    bootstrap_record = _stable_file_record(
        _canonical_regular_file(bootstrap, "confined bootstrap")
    )
    executable_record = _stable_file_record(executable)
    core = {
        "schema_version": SCHEMA_VERSION,
        "status": MANIFEST_STATUS,
        "python_executable": executable_record,
        "bootstrap_relative_path": BOOTSTRAP_RELATIVE_PATH,
        "bootstrap_sha256": bootstrap_record["sha256"],
        "active_root": active.as_posix(),
        "roots": roots,
        "sys_path": approved_sys_path,
        "roots_inventory_sha256": canonical_sha256(roots),
    }
    return {**core, "receipt_sha256": canonical_sha256(core)}


def write_roots_manifest_exclusive(path: Path, manifest: Mapping[str, Any]) -> str:
    """Durably publish one staging manifest and return its physical SHA-256."""

    if set(manifest) != set(_MANIFEST_FIELDS):
        raise ConfinedBootstrapError("root-manifest field inventory differs")
    core = dict(manifest)
    supplied = core.pop("receipt_sha256", None)
    if _require_hex64(supplied, "root-manifest receipt hash") != canonical_sha256(core):
        raise ConfinedBootstrapError("root-manifest self-hash differs")
    destination = Path(os.path.abspath(path.expanduser()))
    parent = _canonical_directory(destination.parent, "root-manifest parent")
    if destination.exists() or destination.is_symlink():
        raise ConfinedBootstrapError("root manifest already exists")
    payload = canonical_json_bytes(dict(manifest)) + b"\n"
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_CLOEXEC | _O_NOFOLLOW,
            0o600,
        )
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise ConfinedBootstrapError("short write publishing root manifest")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        parent_descriptor = os.open(parent, os.O_RDONLY | _O_CLOEXEC)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    except OSError as exc:
        raise ConfinedBootstrapError("could not publish root manifest") from exc
    finally:
        if "descriptor" in locals() and descriptor >= 0:
            os.close(descriptor)
    return hashlib.sha256(payload).hexdigest()


def _validate_root_record(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(_ROOT_FIELDS):
        raise ConfinedBootstrapError("import-root manifest fields differ")
    name = value.get("name")
    role = value.get("role")
    if (
        not isinstance(name, str)
        or _ROOT_NAME.fullmatch(name) is None
        or role not in ("active", "dependency")
        or (index == 0) != (role == "active")
        or (index == 0 and name != "active_root")
    ):
        raise ConfinedBootstrapError("import-root identity differs")
    root = _canonical_directory(Path(str(value.get("path", ""))), f"{name} root")
    observed = inventory_root(name, str(role), root)
    if observed != dict(value):
        raise ConfinedBootstrapError(f"import-root inventory differs: {name}")
    return observed


def validate_roots_manifest(
    manifest_path: Path,
    *,
    expected_file_sha256: str,
    expected_active_root: Path,
) -> dict[str, Any]:
    """Validate the external manifest and every byte reachable via sys.path."""

    expected_digest = _require_hex64(expected_file_sha256, "root-manifest file hash")
    manifest_file = _canonical_regular_file(manifest_path, "root manifest")
    physical_record = _stable_file_record(manifest_file)
    if physical_record["sha256"] != expected_digest:
        raise ConfinedBootstrapError("root-manifest physical SHA-256 differs")
    try:
        physical = manifest_file.read_bytes()
        value = json.loads(physical)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfinedBootstrapError("root manifest is unreadable JSON") from exc
    if hashlib.sha256(physical).hexdigest() != expected_digest:
        raise ConfinedBootstrapError("root manifest changed while being read")
    if not isinstance(value, Mapping) or set(value) != set(_MANIFEST_FIELDS):
        raise ConfinedBootstrapError("root-manifest field inventory differs")
    core = dict(value)
    supplied = core.pop("receipt_sha256", None)
    if _require_hex64(supplied, "root-manifest receipt hash") != canonical_sha256(core):
        raise ConfinedBootstrapError("root-manifest self-hash differs")
    if physical != canonical_json_bytes(dict(value)) + b"\n":
        raise ConfinedBootstrapError("root manifest is not canonical JSON plus newline")
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("status") != MANIFEST_STATUS
    ):
        raise ConfinedBootstrapError("root-manifest identity differs")

    executable = value.get("python_executable")
    if not isinstance(executable, Mapping) or set(executable) != set(
        _EXECUTABLE_FIELDS
    ):
        raise ConfinedBootstrapError("Python executable record differs")
    current_python = _canonical_regular_file(Path(sys.executable), "running Python")
    if _stable_file_record(current_python) != dict(executable):
        raise ConfinedBootstrapError("running Python bytes differ from root manifest")

    active = _canonical_directory(expected_active_root, "expected active root")
    if (
        value.get("active_root") != active.as_posix()
        or value.get("bootstrap_relative_path") != BOOTSTRAP_RELATIVE_PATH
        or _require_hex64(value.get("bootstrap_sha256"), "bootstrap hash")
        != _stable_file_record(
            _canonical_regular_file(Path(__file__), "running bootstrap")
        )["sha256"]
        or Path(__file__).resolve(strict=True) != active / BOOTSTRAP_RELATIVE_PATH
    ):
        raise ConfinedBootstrapError("running bootstrap/active-root binding differs")

    roots_raw = value.get("roots")
    if not isinstance(roots_raw, list) or len(roots_raw) < 2:
        raise ConfinedBootstrapError(
            "root manifest requires active and dependency roots"
        )
    roots = [_validate_root_record(row, index) for index, row in enumerate(roots_raw)]
    names = [str(row["name"]) for row in roots]
    paths = [str(row["path"]) for row in roots]
    if len(names) != len(set(names)) or len(paths) != len(set(paths)):
        raise ConfinedBootstrapError("root manifest contains a duplicate name/path")
    approved_sys_path = value.get("sys_path")
    if (
        not isinstance(approved_sys_path, list)
        or not approved_sys_path
        or any(not isinstance(item, str) for item in approved_sys_path)
        or approved_sys_path[0] != active.as_posix()
        or len(approved_sys_path) != len(set(approved_sys_path))
    ):
        raise ConfinedBootstrapError("root-manifest sys.path order differs")
    canonical_sys_path = [
        _canonical_directory(Path(item), "manifest sys.path root").as_posix()
        for item in approved_sys_path
    ]
    if canonical_sys_path != approved_sys_path or any(
        not any(
            candidate == Path(root_path) or Path(root_path) in candidate.parents
            for root_path in paths
        )
        for candidate in map(Path, approved_sys_path)
    ):
        raise ConfinedBootstrapError("root-manifest sys.path escaped inventories")
    if value.get("roots_inventory_sha256") != canonical_sha256(roots):
        raise ConfinedBootstrapError("combined root inventory hash differs")
    if roots[0]["path"] != active.as_posix():
        raise ConfinedBootstrapError("active-root inventory is not first")
    if any(
        manifest_file == Path(path) or Path(path) in manifest_file.parents
        for path in paths
    ):
        raise ConfinedBootstrapError("root manifest is inside an inventoried root")
    return dict(value)


def validate_startup_state() -> None:
    loaded = sorted(
        name
        for name in sys.modules
        if name.partition(".")[0] in _FORBIDDEN_PREIMPORT_ROOTS
    )
    if sys.flags.no_site != 1:
        raise ConfinedBootstrapError("bootstrap requires Python -S")
    if not sys.dont_write_bytecode:
        raise ConfinedBootstrapError("bootstrap requires Python -B")
    if sys.flags.ignore_environment != 1:
        raise ConfinedBootstrapError("bootstrap requires Python -E")
    if sys.flags.no_user_site != 1:
        raise ConfinedBootstrapError("bootstrap requires Python -s")
    if __package__ not in (None, ""):
        raise ConfinedBootstrapError("bootstrap must run as a direct script")
    if os.environ.get("PYTHONNOUSERSITE") != "1":
        raise ConfinedBootstrapError("bootstrap requires PYTHONNOUSERSITE=1")
    present = [name for name in _FORBIDDEN_STARTUP_ENVIRONMENT if name in os.environ]
    if present:
        raise ConfinedBootstrapError(
            "unsafe bootstrap environment is present: " + ", ".join(present)
        )
    if "site" in sys.modules:
        raise ConfinedBootstrapError("site was imported before confined bootstrap")
    if loaded:
        raise ConfinedBootstrapError(
            "project or ML module loaded before confined bootstrap: "
            + ", ".join(loaded)
        )


class _GuardedLoader:
    def __init__(self, loader: Any, guards: "_ProcessGuards", fullname: str) -> None:
        self._loader = loader
        self._guards = guards
        self._fullname = fullname

    def create_module(self, spec: Any) -> Any:
        creator = getattr(self._loader, "create_module", None)
        return None if creator is None else creator(spec)

    def exec_module(self, module: Any) -> None:
        executor = getattr(self._loader, "exec_module", None)
        if executor is None:
            raise ConfinedBootstrapError("guarded dependency loader has no exec_module")
        executor(module)
        self._guards.patch_loaded_module(self._fullname, module)


class _ProcessGuards:
    def __init__(self) -> None:
        self.forbidden_module_import_attempts = 0
        self.forbidden_startup_import_attempts = 0
        self.torch_module_calls = 0
        self.transformers_model_load_calls = 0
        self.patched_modules: set[str] = set()
        self._module_call_blocker: Any = None
        self._model_load_blocker: Any = None
        self._torch_module_class: Any = None
        self._pretrained_model_class: Any = None
        self._auto_model_class: Any = None

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        del target
        if fullname in _FORBIDDEN_STARTUP_MODULES:
            self.forbidden_startup_import_attempts += 1
            raise ConfinedBootstrapError(
                f"startup customization import is forbidden: {fullname}"
            )
        if any(
            fullname == forbidden or fullname.startswith(forbidden + ".")
            for forbidden in _FORBIDDEN_MODULES
        ):
            self.forbidden_module_import_attempts += 1
            raise ConfinedBootstrapError(f"forbidden recovery import: {fullname}")
        if fullname not in _GUARDED_LOADER_MODULES:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return spec
        spec.loader = _GuardedLoader(spec.loader, self, fullname)
        return spec

    def _blocked_module_call(self, *_args: Any, **_kwargs: Any) -> Any:
        self.torch_module_calls += 1
        raise ConfinedBootstrapError("torch.nn.Module call is forbidden in recovery")

    def _blocked_model_load(self, _cls: Any, *_args: Any, **_kwargs: Any) -> Any:
        self.transformers_model_load_calls += 1
        raise ConfinedBootstrapError("Transformers model load is forbidden in recovery")

    def patch_loaded_module(self, fullname: str, module: Any) -> None:
        if fullname == "torch.nn.modules.module":
            cls = getattr(module, "Module", None)
            if cls is None:
                raise ConfinedBootstrapError("torch Module class is absent")
            if self._module_call_blocker is None:
                self._module_call_blocker = self._blocked_module_call
            cls._call_impl = self._module_call_blocker
            cls._wrapped_call_impl = self._module_call_blocker
            cls.__call__ = self._module_call_blocker
            self._torch_module_class = cls
        elif fullname == "transformers.modeling_utils":
            cls = getattr(module, "PreTrainedModel", None)
            if cls is None:
                raise ConfinedBootstrapError("Transformers PreTrainedModel is absent")
            if self._model_load_blocker is None:
                self._model_load_blocker = self._blocked_model_load
            cls.from_pretrained = classmethod(self._model_load_blocker)
            self._pretrained_model_class = cls
        elif fullname == "transformers.models.auto.auto_factory":
            cls = getattr(module, "_BaseAutoModelClass", None)
            if cls is None:
                raise ConfinedBootstrapError("Transformers auto-model base is absent")
            if self._model_load_blocker is None:
                self._model_load_blocker = self._blocked_model_load
            cls.from_pretrained = classmethod(self._model_load_blocker)
            self._auto_model_class = cls
        else:
            raise ConfinedBootstrapError("unexpected guarded loader module")
        self.patched_modules.add(fullname)

    def prime(self) -> None:
        # The finder was installed before these hash-bound ML imports.  Its
        # loader wrappers patch the callable/model-load boundaries before each
        # import returns to this bootstrap and before any project import.
        importlib.import_module("torch")
        importlib.import_module("transformers.modeling_utils")
        importlib.import_module("transformers.models.auto.auto_factory")
        self.assert_installed()

    @staticmethod
    def _is_bound_method(value: Any, owner: "_ProcessGuards", function: Any) -> bool:
        return getattr(value, "__self__", None) is owner and getattr(
            value, "__func__", None
        ) is getattr(function, "__func__", None)

    def assert_installed(self) -> None:
        if not sys.meta_path or sys.meta_path[0] is not self:
            raise ConfinedBootstrapError("process-lifetime import guard was replaced")
        if self.patched_modules != set(_GUARDED_LOADER_MODULES):
            raise ConfinedBootstrapError("zero-forward loader guard is incomplete")
        cls = self._torch_module_class
        if cls is None or any(
            not self._is_bound_method(value, self, self._module_call_blocker)
            for value in (cls._call_impl, cls._wrapped_call_impl, cls.__call__)
        ):
            raise ConfinedBootstrapError("torch process-lifetime guard was replaced")
        for model_cls in (self._pretrained_model_class, self._auto_model_class):
            descriptor = (
                None if model_cls is None else model_cls.__dict__.get("from_pretrained")
            )
            function = (
                None if descriptor is None else getattr(descriptor, "__func__", None)
            )
            if model_cls is None or function is not self._model_load_blocker:
                raise ConfinedBootstrapError(
                    "Transformers process-lifetime guard was replaced"
                )

    def assert_clean(self) -> None:
        self.assert_installed()
        if (
            self.forbidden_module_import_attempts != 0
            or self.forbidden_startup_import_attempts != 0
            or self.torch_module_calls != 0
            or self.transformers_model_load_calls != 0
        ):
            raise ConfinedBootstrapError("a process-lifetime recovery guard fired")

    def attestation(self) -> dict[str, Any]:
        return {
            "status": "process_lifetime_guards_installed",
            "forbidden_module_import_attempts": self.forbidden_module_import_attempts,
            "forbidden_startup_import_attempts": self.forbidden_startup_import_attempts,
            "torch_module_calls": self.torch_module_calls,
            "transformers_model_load_calls": self.transformers_model_load_calls,
            "patched_modules": sorted(self.patched_modules),
        }


_RUNTIME_STATE: dict[str, Any] | None = None
_GUARDS: _ProcessGuards | None = None


def runtime_attestation() -> dict[str, Any]:
    if _RUNTIME_STATE is None or _GUARDS is None:
        raise ConfinedBootstrapError("bootstrap runtime state is not initialized")
    core = {**_RUNTIME_STATE, "guards": _GUARDS.attestation()}
    return {**core, "receipt_sha256": canonical_sha256(core)}


def _install_only_approved_sys_path(roots: Sequence[str]) -> None:
    if not roots or any(
        not isinstance(path, str)
        or not Path(path).is_absolute()
        or _canonical_directory(Path(path), "approved sys.path root").as_posix() != path
        for path in roots
    ):
        raise ConfinedBootstrapError("approved sys.path roots differ")
    sys.path[:] = list(roots)
    approved = set(roots)
    for cached in tuple(sys.path_importer_cache):
        if cached not in approved:
            sys.path_importer_cache.pop(cached, None)
    if sys.path != list(roots):
        raise ConfinedBootstrapError("sys.path replacement failed")


def _dispatch(mode: str, recovery_argv: Sequence[str], active_root: Path) -> int:
    recovery = importlib.import_module(RECOVERY_MODULE)
    parser = recovery.build_parser()
    args = parser.parse_args([mode, *recovery_argv])
    if args.command != mode:
        raise ConfinedBootstrapError("recovery parser selected a different mode")
    if args.active_root.expanduser().resolve(strict=True) != active_root:
        raise ConfinedBootstrapError("recovery active-root argument differs")
    if args.python_executable.expanduser().resolve(strict=True) != Path(
        sys.executable
    ).resolve(strict=True):
        raise ConfinedBootstrapError("recovery Python argument differs")
    if mode == "preflight-child":
        result = recovery.run_cuda_preflight(args)
    elif mode == "execute-confined":
        result = recovery.execute_recovery(args)
    else:
        raise ConfinedBootstrapError("unknown confined recovery mode")
    print(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--active-root", type=Path, required=True)
    parser.add_argument("--roots-manifest", type=Path, required=True)
    parser.add_argument("--roots-manifest-sha256", required=True)
    parser.add_argument("recovery_argv", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    global _GUARDS, _RUNTIME_STATE  # noqa: PLW0603
    validate_startup_state()
    args = build_parser().parse_args(argv)
    recovery_argv = list(args.recovery_argv)
    if not recovery_argv or recovery_argv.pop(0) != "--":
        raise ConfinedBootstrapError(
            "recovery argv must follow exactly one -- separator"
        )
    active = _canonical_directory(args.active_root, "bootstrap active root")
    if Path.cwd().resolve(strict=True) != active:
        raise ConfinedBootstrapError("bootstrap cwd differs from active root")

    # The deny/loader finder is active before any approved dependency or project
    # import.  Root validation itself remains strictly standard-library-only.
    guards = _ProcessGuards()
    sys.meta_path.insert(0, guards)
    _GUARDS = guards
    manifest = validate_roots_manifest(
        args.roots_manifest,
        expected_file_sha256=args.roots_manifest_sha256,
        expected_active_root=active,
    )
    roots = list(manifest["sys_path"])
    _install_only_approved_sys_path(roots)
    _RUNTIME_STATE = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass_hash_bound_confined_bootstrap",
        "mode": args.mode,
        "pid": os.getpid(),
        "active_root": active.as_posix(),
        "python_executable": Path(sys.executable).resolve(strict=True).as_posix(),
        "roots_manifest_path": args.roots_manifest.resolve(strict=True).as_posix(),
        "roots_manifest_file_sha256": args.roots_manifest_sha256,
        "roots_manifest_receipt_sha256": manifest["receipt_sha256"],
        "roots_inventory_sha256": manifest["roots_inventory_sha256"],
        "sys_path": list(sys.path),
        "bootstrap_sha256": manifest["bootstrap_sha256"],
        "site_imported": "site" in sys.modules,
        "startup_project_or_ml_module_count": 0,
    }
    # Make the already-running direct-script module available as state only;
    # importing it by package name would execute a second, untrusted instance.
    sys.modules[STATE_MODULE] = sys.modules[__name__]
    guards.prime()
    if "site" in sys.modules:
        raise ConfinedBootstrapError("site was imported through approved dependencies")
    guards.assert_clean()
    result = _dispatch(args.mode, recovery_argv, active)
    guards.assert_clean()
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConfinedBootstrapError as exc:
        print(f"confined bootstrap failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
