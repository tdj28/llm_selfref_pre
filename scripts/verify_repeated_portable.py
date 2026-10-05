#!/usr/bin/env python3
"""Read-only entrypoint for the original repeated-paper verifier with exact-pair compatibility."""
from pathlib import Path
import runpy
import sys

if __name__ == "__main__":
    sys.dont_write_bytecode = True
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "experiments/repeat_release_portability.py"),
                  run_name="__main__")
