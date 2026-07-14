from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from experiments.consciousness_readout_validation import guest_attestation, paths


class GuestPreflightWrapperTests(unittest.TestCase):
    WRAPPER = (
        paths.REPO_ROOT
        / "experiments"
        / "consciousness_readout_validation"
        / "run_guest_preflight.sh"
    )

    def test_wrapper_prechecks_source_then_uses_exact_no_bytecode_launch(self):
        source = self.WRAPPER.read_text(encoding="utf-8")
        source_check = source.index('case "${REPO_ROOT}" in')
        bytecode_export = source.index("export PYTHONDONTWRITEBYTECODE=1")
        python_exec = source.index('exec python3 -B -m "${MODULE}"')
        self.assertLess(source_check, bytecode_export)
        self.assertLess(bytecode_export, python_exec)
        self.assertIn("/workspace|/workspace/*)", source)
        self.assertEqual(0o755, stat.S_IMODE(self.WRAPPER.stat().st_mode))
        subprocess.run(["bash", "-n", str(self.WRAPPER)], check=True)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            capture = root / "capture.txt"
            fake_python = fake_bin / "python3"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "{\n"
                "  printf 'ENV=%s\\n' \"${PYTHONDONTWRITEBYTECODE:-unset}\"\n"
                "  printf 'PWD=%s\\n' \"${PWD}\"\n"
                "  for argument in \"$@\"; do printf 'ARG=%s\\n' \"${argument}\"; done\n"
                "} > \"${PREFLIGHT_CAPTURE:?}\"\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            environment = dict(os.environ)
            environment.update(
                {
                    "PATH": f"{fake_bin}:{environment['PATH']}",
                    "PREFLIGHT_CAPTURE": str(capture),
                    "PYTHONDONTWRITEBYTECODE": "wrong-before-wrapper",
                }
            )
            modules = {
                "attest": guest_attestation.GUEST_ATTESTATION_MODULE,
                "stage": guest_attestation.STAGE_PUBLIC_ARTIFACTS_MODULE,
            }
            for mode, module in modules.items():
                with self.subTest(mode=mode):
                    subprocess.run(
                        [str(self.WRAPPER), mode, "--unit-argument"],
                        cwd=root,
                        env=environment,
                        check=True,
                    )
                    self.assertEqual(
                        [
                            "ENV=1",
                            f"PWD={paths.REPO_ROOT.resolve()}",
                            "ARG=-B",
                            "ARG=-m",
                            f"ARG={module}",
                            "ARG=--unit-argument",
                        ],
                        capture.read_text(encoding="utf-8").splitlines(),
                    )

    def test_wrapper_rejects_unknown_mode_before_python(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "capture"
            environment = dict(os.environ)
            environment["PREFLIGHT_CAPTURE"] = str(capture)
            completed = subprocess.run(
                [str(self.WRAPPER), "unknown"],
                cwd=temporary,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("usage:", completed.stderr)
            self.assertFalse(capture.exists())


if __name__ == "__main__":
    unittest.main()
