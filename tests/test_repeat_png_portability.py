"""Zero-tolerance image checks and scoped temporary encoding normalization."""
from copy import deepcopy
import importlib
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import socket

import pytest
from PIL import Image, PngImagePlugin

HERE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("REPEAT_PORTABILITY_ROOT", HERE)).resolve()
spec = importlib.util.spec_from_file_location("repeat_png_portability_under_test", HERE / "experiments/repeat_release_portability.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("PNG compatibility must remain offline")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def png(*, level=6, mode="RGBA", size=(20, 10), software="renderer", pixel=None):
    image = Image.new(mode, size, (20, 40, 60, 255) if mode == "RGBA" else (20, 40, 60))
    if pixel is not None:
        image.putpixel((0, 0), pixel)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Software", software)
    output = BytesIO()
    image.save(output, format="PNG", pnginfo=metadata, dpi=(170, 170), compress_level=level)
    return output.getvalue()


def test_exact_and_alternate_encoding_are_distinguished():
    saved = png()
    exact = c.png_equivalence(saved, saved)
    changed = c.png_equivalence(saved, png(level=0))
    assert exact["exact_file_replay"] and not exact["encoding_normalized"]
    assert not changed["exact_file_replay"] and changed["encoding_normalized"]
    assert exact["rgba_sha256"] == changed["rgba_sha256"]


@pytest.mark.parametrize("kwargs,message", [({"pixel": (21, 40, 60, 255)}, "pixels"),
    ({"pixel": (20, 40, 60, 254)}, "pixels"), ({"software": "other"}, "metadata"),
    ({"mode": "RGB"}, "mode"), ({"size": (10, 20)}, "dimensions")])
def test_content_differences_are_never_normalized(kwargs, message):
    with pytest.raises(ValueError, match=message):
        c.png_equivalence(png(), png(**kwargs))


@pytest.mark.parametrize("a,b", [(1, 1.0), (True, 1), ([1], (1,)),
    ({"dpi": (170, 170)}, {"dpi": (170.0, 170.0)}), ({True: 1}, {1: 1}),
    (0.0, -0.0), (float("nan"), float("nan"))])
def test_metadata_and_data_types_are_exact(a, b):
    assert not c.typed_equal(a, b)


def test_corrupt_png_rejected():
    with pytest.raises((SyntaxError, OSError)):
        c.png_equivalence(png(), png()[:-20])


def test_new_provenance_retains_both_failed_jobs_and_identical_pdfs(tmp_path):
    evidence = c.png_observations()
    assert evidence["original_strict_failure"] == "Rendered figures do not reconstruct"
    assert [row["job_id"] for row in evidence["observations"]] == [111762888000, 111762888118]
    assert all(row["conclusion"] == "failure" for row in evidence["observations"])
    tampered = tmp_path / "evidence.json"
    tampered.write_bytes(c.PNG_EVIDENCE.read_bytes() + b" ")
    with pytest.raises(ValueError, match="sidecar changed"):
        c.png_observations(tampered)


@pytest.fixture
def publication(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    p = importlib.import_module("experiments.repeat_publication")
    data = json.loads((ROOT / c.PACKAGE / "figure_data.json").read_bytes())
    metadata = json.loads((ROOT / c.RELEASE / "RELEASE.json").read_bytes())
    # Existing portability tests run full inference replay. These focused tests
    # retain the original publication verifier and renderer with bound saved data.
    monkeypatch.setattr(p, "_read_verified", lambda *args: (deepcopy(data), deepcopy(metadata)))
    return p, data


def verify(p):
    return p.verify(ROOT / c.RELEASE, ROOT / c.PACKAGE,
                    release_manifest_sha256=c.MANIFEST_SHA, manifest_sha256=c.PACKAGE_SHA)


def alternate_pngs(destination):
    for name in c.PNG_NAMES:
        path = destination / name
        with Image.open(path) as image:
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text("Software", image.info["Software"])
            image.save(path, pnginfo=metadata, dpi=image.info["dpi"], compress_level=0)


def test_original_strict_failure_then_scoped_real_render_normalization(publication, monkeypatch):
    p, data = publication
    original_render, original_verify, original_temporary = p._render, p.verify, p.TemporaryDirectory
    rendered = []
    def different_encoding(data, destination):
        original_render(data, destination)
        rendered.append(destination)
        alternate_pngs(destination)
    monkeypatch.setattr(p, "_render", different_encoding)
    with pytest.raises(p.base.Halted, match="Rendered figures do not reconstruct"):
        verify(p)
    with c.portable_replay(ROOT) as report:
        assert verify(p)["pass"]
    assert len(rendered) == 2 and all(not path.exists() for path in rendered)
    assert len(report["png_replays"]) == 2 and all(row["encoding_normalized"] for row in report["png_replays"])
    assert report["png_original_ci_exact_replay"] == "FAIL"
    assert p._render is different_encoding and p.verify is original_verify and p.TemporaryDirectory is original_temporary
    assert str(ROOT) not in json.dumps(report)


@pytest.mark.parametrize("change", ["pixel", "metadata", "pdf"])
def test_real_render_tamper_and_error_restore(publication, monkeypatch, change):
    p, _ = publication
    original_render, original_verify, original_temporary = p._render, p.verify, p.TemporaryDirectory
    def damaged(data, destination):
        original_render(data, destination)
        if change == "pdf":
            path = destination / "repeated_main.pdf"
            path.write_bytes(path.read_bytes() + b" ")
        else:
            path = destination / "repeated_main.png"
            with Image.open(path) as image:
                metadata = PngImagePlugin.PngInfo()
                metadata.add_text("Software", "changed" if change == "metadata" else image.info["Software"])
                if change == "pixel":
                    image.putpixel((0, 0), (0, 0, 0, 255))
                image.save(path, pnginfo=metadata, dpi=image.info["dpi"])
    monkeypatch.setattr(p, "_render", damaged)
    error, message = (p.base.Halted, "Rendered figures") if change == "pdf" else (ValueError, "PNG " + change)
    with pytest.raises(error, match=message):
        with c.portable_replay(ROOT):
            verify(p)
    assert p._render is damaged and p.verify is original_verify and p.TemporaryDirectory is original_temporary


def test_unbound_data_rejected_before_render(publication, monkeypatch):
    p, data = publication
    called = []
    def strict(source, destination, **kwargs):
        with p.TemporaryDirectory(prefix="repeat-figure-verify-") as temporary:
            changed = deepcopy(data)
            changed["unbound"] = True
            p._render(changed, Path(temporary))
    monkeypatch.setattr(p, "verify", strict)
    monkeypatch.setattr(p, "_render", lambda *args: called.append(True))
    with c.portable_replay(ROOT):
        with pytest.raises(ValueError, match="Unbound PNG figure data"):
            verify(p)
    assert not called


def test_never_normalize_outside_verifier_owned_directory(publication, monkeypatch, tmp_path):
    p, data = publication
    def strict(source, destination, **kwargs):
        p._render(data, tmp_path)
    monkeypatch.setattr(p, "verify", strict)
    with c.portable_replay(ROOT):
        with pytest.raises(ValueError, match="verifier-owned"):
            verify(p)
    assert not list(tmp_path.iterdir())


def test_unbound_publication_cannot_normalize(publication, monkeypatch, tmp_path):
    p, data = publication
    original_render = p._render
    observed = []
    def different_encoding(data, destination):
        original_render(data, destination)
        alternate_pngs(destination)
    def strict(source, destination, **kwargs):
        with p.TemporaryDirectory(prefix="repeat-figure-verify-") as temporary:
            p._render(data, Path(temporary))
            observed.append((Path(temporary) / c.PNG_NAMES[0]).read_bytes())
    monkeypatch.setattr(p, "verify", strict)
    monkeypatch.setattr(p, "_render", different_encoding)
    with c.portable_replay(ROOT) as report:
        p.verify(ROOT / c.RELEASE, tmp_path, release_manifest_sha256=c.MANIFEST_SHA, manifest_sha256=c.PACKAGE_SHA)
        p.verify(ROOT / c.RELEASE, ROOT / c.PACKAGE, release_manifest_sha256=c.MANIFEST_SHA, manifest_sha256="0" * 64)
    assert not report["png_replays"]
    assert all(raw != (ROOT / c.PACKAGE / c.PNG_NAMES[0]).read_bytes() for raw in observed)


def test_renderer_exception_restores_all_wrappers(publication, monkeypatch):
    p, _ = publication
    original_verify, original_temporary = p.verify, p.TemporaryDirectory
    def broken(*args):
        raise RuntimeError("render failed")
    monkeypatch.setattr(p, "_render", broken)
    with pytest.raises(RuntimeError, match="render failed"):
        with c.portable_replay(ROOT):
            verify(p)
    assert p._render is broken and p.verify is original_verify and p.TemporaryDirectory is original_temporary
