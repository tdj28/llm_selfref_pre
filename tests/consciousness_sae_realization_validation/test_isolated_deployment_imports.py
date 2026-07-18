from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from experiments.consciousness_sae_realization_validation import build_plan


REPO_ROOT = Path(__file__).resolve().parents[2]
SUCCESSOR_PACKAGE = "experiments.consciousness_sae_realization_validation"


class IsolatedDeploymentImportTests(unittest.TestCase):
    def test_exact_source_allowlist_imports_every_guest_cli_without_ambient_repo(self) -> None:
        predecessor = tuple(
            path
            for path in build_plan.BOUND_SOURCE_PATHS
            if path.startswith("experiments/consciousness_readout_validation/")
        )
        self.assertEqual(
            predecessor,
            (
                "experiments/consciousness_readout_validation/runpod_lifecycle.py",
            ),
        )
        self.assertFalse(
            any(
                marker in path
                for path in build_plan.BOUND_SOURCE_PATHS
                for marker in (
                    "/fixtures.py",
                    "/tokenizer_audit.py",
                    "consciousness_sae_changepoint",
                )
            )
        )
        runtime_source = (
            REPO_ROOT
            / "experiments/consciousness_sae_realization_validation/runtime.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("experiments.consciousness_readout_validation", runtime_source)
        self.assertNotIn("experiments.consciousness_sae_changepoint", runtime_source)
        launcher_source = (
            REPO_ROOT
            / "experiments/consciousness_sae_realization_validation/guest_launcher.py"
        ).read_text(encoding="utf-8")
        for forbidden_import in (
            " import runtime",
            " import runner",
            "import torch",
            "import transformers",
        ):
            self.assertNotIn(forbidden_import, launcher_source)

        with tempfile.TemporaryDirectory() as directory:
            guest = Path(directory).resolve()
            for relative in build_plan.BOUND_SOURCE_PATHS:
                source = REPO_ROOT / relative
                destination = guest / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

            expected = set(build_plan.BOUND_SOURCE_PATHS)
            observed = {
                path.relative_to(guest).as_posix()
                for path in guest.rglob("*")
                if path.is_file()
            }
            self.assertEqual(observed, expected)

            environment = {
                key: value
                for key, value in os.environ.items()
                if key not in {"PYTHONPATH", "PYTHONHOME"}
            }
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            for cli_name in build_plan.GUEST_CLI_MODULES:
                module = f"{SUCCESSOR_PACKAGE}.{cli_name}"
                # -I removes cwd, PYTHONPATH, user site, and the host repo from
                # sys.path.  The one inserted path is the controlled fresh guest.
                code = (
                    "import pathlib,runpy,sys;"
                    f"guest=pathlib.Path({str(guest)!r}).resolve();"
                    f"ambient=pathlib.Path({str(REPO_ROOT)!r}).resolve();"
                    "assert all(pathlib.Path(p or '.').resolve()!=ambient for p in sys.path);"
                    "sys.path.insert(0,str(guest));"
                    f"sys.argv=[{module!r},'--help'];"
                    f"runpy.run_module({module!r},run_name='__main__')"
                )
                completed = subprocess.run(
                    [sys.executable, "-I", "-B", "-c", code],
                    cwd=Path("/"),
                    env=environment,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    msg=(
                        f"isolated --help failed for {module}:\n"
                        f"stdout={completed.stdout}\nstderr={completed.stderr}"
                    ),
                )
            self.assertEqual(list(guest.rglob("__pycache__")), [])
            self.assertEqual(list(guest.rglob("*.pyc")), [])

            order_code = "\n".join(
                (
                    "import pathlib, sys",
                    f"guest = pathlib.Path({str(guest)!r}).resolve()",
                    "sys.path.insert(0, str(guest))",
                    "from experiments.consciousness_sae_realization_validation "
                    "import guest_launcher as launcher",
                    "assert 'torch' not in sys.modules",
                    "assert 'transformers' not in sys.modules",
                    "try:",
                    "    launcher._require_pre_model_process(('torch',))",
                    "except launcher.GuestLaunchError:",
                    "    pass",
                    "else:",
                    "    raise AssertionError('early Torch import was accepted')",
                )
            )
            completed = subprocess.run(
                [sys.executable, "-I", "-B", "-c", order_code],
                cwd=Path("/"),
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=f"isolated launcher order check failed: {completed.stderr}",
            )


if __name__ == "__main__":
    unittest.main()
