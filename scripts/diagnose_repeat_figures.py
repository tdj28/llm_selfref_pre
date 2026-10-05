#!/usr/bin/env python3
"""Offline figure-byte diagnostic, not publication acceptance or numerical replay.

Render the bound saved figure data with the unchanged renderer in temporary
storage. Exit 0 for exact file replay, 1 for differing bytes, or 2 for invalid
inputs/replay failure. Never rewrite a figure, binding, or strict failure record.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import zlib

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def byte_comparison(saved, replay):
    return {"saved_sha256": sha(saved), "replay_sha256": sha(replay),
            "saved_bytes": len(saved), "replay_bytes": len(replay), "exact": saved == replay}


def png_comparison(saved, replay):
    import numpy as np
    from PIL import Image

    arrays, details = [], []
    for path in (saved, replay):
        with Image.open(path) as image:
            image.load()
            array = np.array(image.convert("RGBA"), dtype=np.uint8)
            arrays.append(array)
            details.append({"dimensions": list(image.size), "mode": image.mode,
                            "rgba_sha256": sha(array.tobytes()),
                            "metadata": {key: {"type": type(value).__name__,
                                               "sha256": sha(repr(value).encode())}
                                         for key, value in sorted(image.info.items())}})
    result = {"saved": details[0], "replay": details[1], "comparison_mode": "RGBA",
              "same_dimensions": arrays[0].shape == arrays[1].shape}
    if not result["same_dimensions"]:
        result.update(pixels_equal=False, changed_pixels=None, changed_channels=None,
                      max_absolute_channel_delta=None, mean_absolute_channel_delta=None)
        return result
    delta = np.abs(arrays[0].astype(np.int16) - arrays[1].astype(np.int16))
    changed = int(np.count_nonzero(np.any(delta, axis=2)))
    result.update(pixels_equal=changed == 0, changed_pixels=changed,
                  changed_channels=int(np.count_nonzero(delta)), total_pixels=int(delta.shape[0] * delta.shape[1]),
                  max_absolute_channel_delta=int(delta.max()), mean_absolute_channel_delta=float(delta.mean()))
    return result


def _command(args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=30, check=False, env={**os.environ, "LC_ALL": "C"})


def _geometry(raw):
    text = raw.decode("utf-8", errors="strict")
    pages = re.search(r"^Pages:\s+(\d+)\s*$", text, re.MULTILINE)
    lines = [" ".join(line.split()) for line in text.splitlines()
             if re.match(r"^Page\s+\d+\s+(?:size:|rot:|(?:Media|Crop|Bleed|Trim|Art)Box:)", line)]
    if pages is None or not 1 <= int(pages[1]) <= 32 or not lines:
        raise ValueError("Unrecognized or oversized PDF geometry")
    return {"pages": int(pages[1]), "page_geometry": lines}


def pdf_comparison(saved, replay):
    result = {}
    for name, options, key in (("pdftotext", ["-layout", "-enc", "UTF-8"], "text"),
                               ("pdffonts", [], "fonts"),
                               ("pdfinfo", ["-box", "-f", "1", "-l", "32"], "info")):
        binary = shutil.which(name)
        if binary is None:
            result[key] = {"status": "unavailable"}
            continue
        try:
            version = _command([binary, "-v"])
            match = re.search(rb"\bversion\s+([0-9][\w.+-]*)", version.stdout + version.stderr)
            pair = [_command([binary, *options, str(path), *(["-"] if key == "text" else [])])
                    for path in (saved, replay)]
            if any(row.returncode for row in pair):
                result[key] = {"status": "error", "returncodes": [row.returncode for row in pair]}
                continue
            result[key] = {"status": "ok", "version": match[1].decode() if match else None,
                           **byte_comparison(pair[0].stdout, pair[1].stdout)}
            if key == "info":
                a, b = (_geometry(row.stdout) for row in pair)
                result["geometry"] = {"status": "ok", "saved": a, "replay": b, "exact": a == b}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            result[key] = {"status": "error"}
    return result


def renderer_versions():
    import matplotlib
    from matplotlib import font_manager, ft2font
    import PIL
    from PIL import features

    result = {"matplotlib": matplotlib.__version__, "pillow": PIL.__version__,
              "freetype": ft2font.__freetype_version__, "backend": str(matplotlib.get_backend()),
              "python_zlib_runtime": zlib.ZLIB_RUNTIME_VERSION, "pillow_zlib": features.version("zlib"),
              "dejavu_sans_file_sha256": sha(Path(font_manager.findfont("DejaVu Sans")).read_bytes())}
    for name in ("numpy", "fonttools"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def diagnose(root=ROOT):
    root = Path(root).resolve()
    sys.path.insert(0, str(root))
    try:
        guard = importlib.import_module("experiments.repeat_release_portability")
        if Path(guard.__file__).resolve() != root / "experiments/repeat_release_portability.py":
            raise ValueError("Input checker imported from another checkout")
        evidence = root / "provenance/repeated_release_portability.json"
        # Input hashing only: do not enter the numerical portability context.
        guard.verify_inputs(root, evidence)
        renderer = importlib.import_module("experiments.repeat_publication")
        if Path(renderer.__file__).resolve() != root / "experiments/repeat_publication.py":
            raise ValueError("Renderer imported from another checkout")
        source = root / guard.PACKAGE
        data_bytes = (source / "figure_data.json").read_bytes()
        with TemporaryDirectory(prefix="repeat-figure-diagnostic-") as temporary:
            destination = Path(temporary)
            renderer._render(json.loads(data_bytes), destination)
            files = {}
            for name in renderer.FIGURES:
                for ext in (".png", ".pdf"):
                    saved, replay = source / (name + ext), destination / (name + ext)
                    files[name + ext] = byte_comparison(saved.read_bytes(), replay.read_bytes())
                    files[name + ext]["decoded"] = (png_comparison if ext == ".png" else pdf_comparison)(saved, replay)
            versions = renderer_versions()
        guard.verify_inputs(root, evidence)
        return {"schema": "repeated-figure-exact-diagnostic-v1", "python": platform.python_version(),
                "system": platform.system(), "machine": platform.machine(), "versions": versions,
                "publication_manifest_sha256": guard.PACKAGE_SHA, "release_manifest_sha256": guard.MANIFEST_SHA,
                "figure_data_sha256": sha(data_bytes), "files": files,
                "exact_replay": all(row["exact"] for row in files.values()),
                "scope": "Diagnostic only: saved figure data rendered; no numerical replay, tolerance or publication acceptance; PDF summaries are not full visual equivalence"}
    finally:
        sys.path.pop(0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        captured = io.StringIO()
        with redirect_stderr(captured), redirect_stdout(captured):
            result = diagnose(args.root)
        raw = captured.getvalue().encode()
        result["captured_library_output"] = {"bytes": len(raw), "sha256": sha(raw)}
    except Exception as exc:
        # Exception messages and subprocess stderr can contain private local paths.
        print(json.dumps({"schema": "repeated-figure-exact-diagnostic-v1",
                          "diagnostic_error": type(exc).__name__}))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result["exact_replay"] else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    def offline(event, args):
        if event in ("socket.connect", "socket.getaddrinfo"):
            raise RuntimeError("Figure diagnostic is offline")
    sys.addaudithook(offline)
    raise SystemExit(main())
