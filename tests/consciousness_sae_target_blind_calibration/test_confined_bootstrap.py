from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.consciousness_sae_target_blind_calibration import confined_bootstrap


PYTHON_EXECUTABLE = Path(sys.executable).resolve()


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fake_roots(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    active = (tmp_path / "active").resolve()
    dependency = (tmp_path / "dependency").resolve()
    manifest_path = (tmp_path / "manifests/ROOTS.json").resolve()
    observed = (tmp_path / "observed.json").resolve()

    bootstrap_path = active / confined_bootstrap.BOOTSTRAP_RELATIVE_PATH
    bootstrap_path.parent.mkdir(parents=True)
    shutil.copyfile(Path(confined_bootstrap.__file__), bootstrap_path)
    _write(active / "experiments/__init__.py")
    _write(
        active / "experiments/consciousness_sae_target_blind_calibration/__init__.py"
    )
    _write(
        active
        / "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
        """\
import argparse
import json
import sys
from pathlib import Path

STATE = sys.modules['_consciousness_sae_confined_bootstrap_state']
IMPORT_ATTESTATION = STATE.runtime_attestation()
if IMPORT_ATTESTATION['guards']['status'] != 'process_lifetime_guards_installed':
    raise RuntimeError('guards were not installed before project import')
if IMPORT_ATTESTATION['site_imported'] or 'site' in sys.modules:
    raise RuntimeError('site was imported')


def build_parser():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('preflight-child', 'execute-confined'):
        child = commands.add_parser(name)
        child.add_argument('--active-root', type=Path, required=True)
        child.add_argument('--python-executable', type=Path, required=True)
        child.add_argument('--output', type=Path, required=True)
        child.add_argument(
            '--exercise',
            choices=('none', 'module', 'model-load', 'forbidden-import', 'site-import'),
            default='none',
        )
    return parser


def _run(args):
    if args.exercise == 'module':
        from torch.nn.modules.module import Module
        try:
            Module()()
        except RuntimeError:
            pass
    elif args.exercise == 'model-load':
        from transformers.modeling_utils import PreTrainedModel
        try:
            PreTrainedModel.from_pretrained('forbidden')
        except RuntimeError:
            pass
    elif args.exercise == 'forbidden-import':
        try:
            __import__('experiments.consciousness_sae_target_blind_calibration.runner')
        except RuntimeError:
            pass
    elif args.exercise == 'site-import':
        try:
            __import__('site')
        except RuntimeError:
            pass
    args.output.write_text(json.dumps(STATE.runtime_attestation()), encoding='utf-8')
    return args.output


def run_cuda_preflight(args):
    return _run(args)


def execute_recovery(args):
    return _run(args)
""",
    )

    _write(dependency / "torch/__init__.py", "from . import nn\n")
    _write(dependency / "torch/nn/__init__.py", "from .modules.module import Module\n")
    _write(dependency / "torch/nn/modules/__init__.py")
    _write(
        dependency / "torch/nn/modules/module.py",
        """\
class Module:
    def _call_impl(self, *args, **kwargs):
        return 'unguarded-module-call'
    _wrapped_call_impl = _call_impl
    __call__ = _wrapped_call_impl
""",
    )
    _write(dependency / "transformers/__init__.py")
    _write(
        dependency / "transformers/modeling_utils.py",
        """\
from torch.nn.modules.module import Module
class PreTrainedModel(Module):
    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        return cls()
""",
    )
    _write(dependency / "transformers/models/__init__.py")
    _write(dependency / "transformers/models/auto/__init__.py")
    _write(
        dependency / "transformers/models/auto/auto_factory.py",
        """\
class _BaseAutoModelClass:
    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        return object()
""",
    )
    site_marker = tmp_path / "sitecustomize-ran"
    _write(
        dependency / "sitecustomize.py",
        f"from pathlib import Path\nPath({site_marker.as_posix()!r}).write_text('ran')\n",
    )

    manifest = confined_bootstrap.build_roots_manifest(
        python_executable=PYTHON_EXECUTABLE,
        active_root=active,
        dependency_roots=(("approved_dependencies", dependency),),
    )
    manifest_path.parent.mkdir(parents=True)
    physical_sha256 = confined_bootstrap.write_roots_manifest_exclusive(
        manifest_path, manifest
    )
    assert physical_sha256 == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return active, manifest_path, observed, site_marker


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in confined_bootstrap._FORBIDDEN_STARTUP_ENVIRONMENT:
        environment.pop(name, None)
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def _run_bootstrap(
    active: Path,
    manifest_path: Path,
    observed: Path,
    *,
    mode: str = "preflight-child",
    exercise: str = "none",
    manifest_sha256: str | None = None,
) -> subprocess.CompletedProcess[str]:
    bootstrap = active / confined_bootstrap.BOOTSTRAP_RELATIVE_PATH
    digest = manifest_sha256 or hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return subprocess.run(
        [
            PYTHON_EXECUTABLE.as_posix(),
            "-B",
            "-E",
            "-s",
            "-S",
            bootstrap.as_posix(),
            "--mode",
            mode,
            "--active-root",
            active.as_posix(),
            "--roots-manifest",
            manifest_path.as_posix(),
            "--roots-manifest-sha256",
            digest,
            "--",
            "--active-root",
            active.as_posix(),
            "--python-executable",
            PYTHON_EXECUTABLE.as_posix(),
            "--output",
            observed.as_posix(),
            "--exercise",
            exercise,
        ],
        cwd=active,
        env=_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=30,
    )


def test_bootstrap_source_imports_only_stdlib() -> None:
    source = Path(confined_bootstrap.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}
    assert not ({"experiments", "numpy", "torch", "transformers"} & imported)


def test_direct_no_site_bootstrap_validates_roots_installs_guards_and_dispatches(
    tmp_path: Path,
) -> None:
    active, manifest, observed, site_marker = _fake_roots(tmp_path)
    result = _run_bootstrap(active, manifest, observed)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == observed.as_posix()
    assert not site_marker.exists()
    attestation = json.loads(observed.read_text(encoding="utf-8"))
    assert attestation["status"] == "pass_hash_bound_confined_bootstrap"
    assert attestation["mode"] == "preflight-child"
    assert attestation["site_imported"] is False
    assert attestation["sys_path"] == [
        active.as_posix(),
        (tmp_path / "dependency").resolve().as_posix(),
    ]
    assert attestation["guards"] == {
        "status": "process_lifetime_guards_installed",
        "forbidden_module_import_attempts": 0,
        "forbidden_startup_import_attempts": 0,
        "torch_module_calls": 0,
        "transformers_model_load_calls": 0,
        "patched_modules": sorted(confined_bootstrap._GUARDED_LOADER_MODULES),
    }


@pytest.mark.parametrize(
    "exercise", ["module", "model-load", "forbidden-import", "site-import"]
)
def test_bootstrap_fails_if_any_process_lifetime_guard_fires(
    tmp_path: Path, exercise: str
) -> None:
    active, manifest, observed, _site_marker = _fake_roots(tmp_path)
    result = _run_bootstrap(active, manifest, observed, exercise=exercise)
    assert result.returncode == 2
    assert "process-lifetime recovery guard fired" in result.stderr


def test_execute_mode_uses_the_same_bootstrap_path(tmp_path: Path) -> None:
    active, manifest, observed, _site_marker = _fake_roots(tmp_path)
    result = _run_bootstrap(active, manifest, observed, mode="execute-confined")
    assert result.returncode == 0, result.stderr
    assert (
        json.loads(observed.read_text(encoding="utf-8"))["mode"] == "execute-confined"
    )


def test_bootstrap_rejects_root_or_manifest_tampering(tmp_path: Path) -> None:
    active, manifest, observed, _site_marker = _fake_roots(tmp_path)
    approved_manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
    with pytest.raises(
        confined_bootstrap.ConfinedBootstrapError, match="already exists"
    ):
        confined_bootstrap.write_roots_manifest_exclusive(
            manifest, json.loads(manifest.read_text(encoding="utf-8"))
        )
    (active / "unexpected.py").write_text("UNBOUND = True\n", encoding="utf-8")
    changed_root = _run_bootstrap(
        active,
        manifest,
        observed,
        manifest_sha256=approved_manifest_hash,
    )
    assert changed_root.returncode == 2
    assert "import-root inventory differs" in changed_root.stderr

    (active / "unexpected.py").unlink()
    manifest.write_bytes(manifest.read_bytes() + b" ")
    changed_manifest = _run_bootstrap(
        active,
        manifest,
        observed,
        manifest_sha256=approved_manifest_hash,
    )
    assert changed_manifest.returncode == 2
    assert "root-manifest physical SHA-256 differs" in changed_manifest.stderr


def test_manifest_builder_rejects_symlink_and_hardlink_dependency_bytes(
    tmp_path: Path,
) -> None:
    dependency = tmp_path / "dependency"
    dependency.mkdir()
    source = dependency / "source.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    symlink = dependency / "link.py"
    symlink.symlink_to(source.name)
    with pytest.raises(confined_bootstrap.ConfinedBootstrapError, match="symlink"):
        confined_bootstrap.inventory_root("dependency", "dependency", dependency)
    symlink.unlink()
    hardlink = dependency / "hard.py"
    os.link(source, hardlink)
    with pytest.raises(confined_bootstrap.ConfinedBootstrapError, match="hard-linked"):
        confined_bootstrap.inventory_root("dependency", "dependency", dependency)


def test_bootstrap_requires_exact_direct_interpreter_flags(tmp_path: Path) -> None:
    script = Path(confined_bootstrap.__file__).resolve()
    environment = _environment()
    cases = [
        (["-B", "-E", "-s"], "requires Python -S"),
        (["-E", "-s", "-S"], "requires Python -B"),
        (["-B", "-s", "-S"], "requires Python -E"),
        (["-B", "-E", "-S"], "requires Python -s"),
    ]
    for flags, expected in cases:
        result = subprocess.run(
            [PYTHON_EXECUTABLE.as_posix(), *flags, script.as_posix(), "--help"],
            cwd=tmp_path,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        assert result.returncode == 2
        assert expected in result.stderr
    exact = subprocess.run(
        [
            PYTHON_EXECUTABLE.as_posix(),
            "-B",
            "-E",
            "-s",
            "-S",
            script.as_posix(),
            "--help",
        ],
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert exact.returncode == 0, exact.stderr
