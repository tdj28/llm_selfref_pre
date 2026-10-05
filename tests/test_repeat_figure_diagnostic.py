"""Diagnostics measure exact differences without accepting or changing artifacts."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image, PngImagePlugin

HERE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("REPEAT_PORTABILITY_ROOT", HERE)).resolve()
spec = importlib.util.spec_from_file_location("repeat_figure_diagnostic", HERE / "scripts/diagnose_repeat_figures.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Diagnostic must remain offline")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def images(tmp_path, size=(3, 2)):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    Image.new("RGBA", size, (12, 30, 40, 255)).save(a)
    b.write_bytes(a.read_bytes())
    return a, b


def test_exact_png(tmp_path):
    a, b = images(tmp_path)
    report = d.png_comparison(a, b)
    assert report["pixels_equal"] and report["changed_pixels"] == 0
    assert report["total_pixels"] == 6 and report["max_absolute_channel_delta"] == 0
    assert report["saved"] == report["replay"]


def test_metadata_only_is_measured_not_accepted(tmp_path):
    a, b = images(tmp_path)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Software", "/private/hidden/path")
    with Image.open(a) as image:
        image.save(b, pnginfo=metadata)
    report = d.png_comparison(a, b)
    assert report["pixels_equal"] and report["saved"]["metadata"] != report["replay"]["metadata"]
    assert not d.byte_comparison(a.read_bytes(), b.read_bytes())["exact"]
    assert "/private/hidden" not in json.dumps(report)


def test_one_channel_change_has_exact_counts(tmp_path):
    a, b = images(tmp_path)
    with Image.open(b) as image:
        image.putpixel((1, 0), (19, 30, 40, 255))
        image.save(b)
    report = d.png_comparison(a, b)
    assert not report["pixels_equal"] and report["changed_pixels"] == report["changed_channels"] == 1
    assert report["max_absolute_channel_delta"] == 7
    assert report["mean_absolute_channel_delta"] == 7 / 24


def test_dimensions_not_resized_or_compared(tmp_path):
    a, b = images(tmp_path)
    Image.new("RGBA", (2, 3)).save(b)
    report = d.png_comparison(a, b)
    assert not report["same_dimensions"] and not report["pixels_equal"]
    assert report["changed_pixels"] is None


def test_modes_explicit_and_alpha_compared(tmp_path):
    a, b = images(tmp_path)
    with Image.open(a) as image:
        image.convert("RGB").save(b)
    report = d.png_comparison(a, b)
    assert report["pixels_equal"] and report["saved"]["mode"] != report["replay"]["mode"]
    with Image.open(a) as image:
        image.putpixel((0, 0), (12, 30, 40, 254))
        image.save(b)
    assert d.png_comparison(a, b)["changed_channels"] == 1


INFO = b"Creator: public renderer\nPages: 1\nPage 1 size: 475.2 x 446.4 pts\nPage 1 rot: 0\nPage 1 MediaBox: 0 0 475.2 446.4\n"


def test_poppler_missing_explicit(monkeypatch):
    monkeypatch.setattr(d.shutil, "which", lambda name: None)
    assert all(row["status"] == "unavailable" for row in d.pdf_comparison(Path("a"), Path("b")).values())


@pytest.mark.parametrize("failure", ["exit", "timeout", "os"])
def test_poppler_errors_do_not_print_paths(monkeypatch, failure):
    monkeypatch.setattr(d.shutil, "which", lambda name: "/private/bin/" + name)
    def command(args):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, 30, stderr=b"private path")
        if failure == "os":
            raise OSError("/private/path")
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"/private/path")
    monkeypatch.setattr(d, "_command", command)
    report = d.pdf_comparison(Path("a"), Path("b"))
    assert all(row["status"] == "error" for row in report.values())
    assert "private" not in json.dumps(report)


def test_poppler_exact_text_fonts_and_different_geometry(monkeypatch):
    monkeypatch.setattr(d.shutil, "which", lambda name: name)
    def command(args):
        output = b"private figure text"
        if args[-1] == "-v":
            output = b"pdfinfo version 26.01.0"
        elif args[0] == "pdfinfo":
            output = INFO if args[-1] == "a" else INFO.replace(b"446.4", b"446.5")
        return SimpleNamespace(returncode=0, stdout=output, stderr=b"")
    monkeypatch.setattr(d, "_command", command)
    report = d.pdf_comparison(Path("a"), Path("b"))
    assert report["text"]["exact"] and report["fonts"]["exact"]
    assert not report["geometry"]["exact"] and not report["info"]["exact"]
    assert report["text"]["version"] == "26.01.0"
    assert "private figure text" not in json.dumps(report)


@pytest.mark.parametrize("raw", [b"", b"Pages: 1", INFO.replace(b"Pages: 1", b"Pages: 33")])
def test_missing_or_oversized_geometry_rejected(raw):
    with pytest.raises(ValueError):
        d._geometry(raw)


@pytest.mark.parametrize("exact,code", [(True, 0), (False, 1)])
def test_exit_status_retains_byte_mismatch(monkeypatch, capsys, exact, code):
    monkeypatch.setattr(d, "diagnose", lambda root: {"exact_replay": exact})
    assert d.main([]) == code
    assert json.loads(capsys.readouterr().out)["exact_replay"] is exact


def test_error_message_never_exposes_private_paths(monkeypatch, capsys):
    def failed(root):
        raise ValueError("/private/local/path")
    monkeypatch.setattr(d, "diagnose", failed)
    assert d.main([]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["diagnostic_error"] == "ValueError" and "private" not in json.dumps(report)


def test_library_messages_are_hashed_not_printed(monkeypatch, capsys):
    def noisy(root):
        print("/private/local/font-cache", file=d.sys.stderr)
        print("raw library output")
        return {"exact_replay": True}
    monkeypatch.setattr(d, "diagnose", noisy)
    assert d.main([]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert not captured.err and "private" not in captured.out and "raw library output" not in captured.out
    assert report["captured_library_output"]["bytes"] > 0


def test_binding_failure_prevents_renderer_import(monkeypatch, tmp_path):
    calls = []
    def reject(root, evidence):
        calls.append("bindings")
        raise ValueError("Bound artifact changed")
    guard = SimpleNamespace(__file__=tmp_path / "experiments/repeat_release_portability.py", verify_inputs=reject)
    def imported(name):
        calls.append(name)
        assert name == "experiments.repeat_release_portability"
        return guard
    monkeypatch.setattr(d.importlib, "import_module", imported)
    before = list(d.sys.path)
    with pytest.raises(ValueError, match="Bound artifact"):
        d.diagnose(tmp_path)
    assert calls == ["experiments.repeat_release_portability", "bindings"]
    assert d.sys.path == before


def test_other_checkout_import_rejected(monkeypatch, tmp_path):
    guard = SimpleNamespace(__file__=tmp_path / "other/experiments/repeat_release_portability.py")
    monkeypatch.setattr(d.importlib, "import_module", lambda name: guard)
    with pytest.raises(ValueError, match="another checkout"):
        d.diagnose(tmp_path)


def test_actual_bound_figures_offline_and_unchanged():
    report = d.diagnose(ROOT)
    assert len(report["files"]) == 4
    assert report["exact_replay"] == all(row["exact"] for row in report["files"].values())
    assert report["versions"]["matplotlib"] and report["versions"]["pillow"] and report["versions"]["freetype"]
    for name, row in report["files"].items():
        assert len(row["saved_sha256"]) == len(row["replay_sha256"]) == 64
        if name.endswith(".png"):
            assert row["decoded"]["saved"]["dimensions"][0] > 0
    assert str(ROOT) not in json.dumps(report)
