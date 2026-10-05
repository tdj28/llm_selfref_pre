#!/usr/bin/env python3
"""Offline verification of the single evidence-bound Kolibri publication."""
from pathlib import Path
import runpy
import sys

if __name__ == "__main__":
    sys.dont_write_bytecode = True
    namespace = runpy.run_path(str(Path(__file__).resolve().parents[1]
                                  / "experiments/kolibri_wilson_portability.py"))
    raise SystemExit(namespace["main"]())
