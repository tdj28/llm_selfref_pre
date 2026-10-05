"""Synthetic source/archive tests; no manuscript edits or network calls."""
import io
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tarfile

import pytest

from scripts import build_arxiv_bundle as b


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Packaging tests must remain offline")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def source(tmp_path):
    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "\\begin{abstract}A synthetic abstract.\\end{abstract}\n"
        "\\section{Introduction}\\label{intro}\n"
        "Alpha% private comment\nBeta. 20\\% retained.\n"
        "\\input{section}\n\\bibliographystyle{plain}\n"
        "\\bibliography{references}\n\\end{document}\n")
    (paper / "section.tex").write_text("See Section~\\ref{intro} and \\cite{test}.\n")
    (paper / "main.bbl").write_text(
        "\\begin{thebibliography}{1}\n% private bibliography comment\n"
        "\\bibitem{test}A. Author. Synthetic reference. 2026.\n\\end{thebibliography}\n")
    (paper / "references.bib").write_text("% Private bibliography notes excluded entirely\n")
    return tmp_path


def append_source(root, text):
    path = root / "paper/section.tex"
    path.write_text(path.read_text() + text)


@pytest.mark.parametrize("raw,expected", [
    ("a% secret\nb", "a%\nb"),
    ("a % secret\n  b", "a %\n  b"),
    ("a\n% comment-only\nb", "a\n%\nb"),
    ("a% secret\r\nb", "a%\r\nb"),
    ("a% EOF", "a%"),
    (r"20\% real % secret", r"20\% real %"),
    (r"line\\% secret", r"line\\%"),
    (r"line\\\% real % secret", r"line\\\% real %"),
    ("% \\input{missing} \\catcode bad\nOK", "%\nOK"),
])
def test_comment_sanitization_preserves_tex_whitespace(raw, expected):
    assert b.sanitize(raw) == expected


@pytest.mark.parametrize("text", [r"\verb|literal%text|", r"\catcode`\%=12",
    r"\begin{verbatim}literal%text\end{verbatim}", r"\begin{comment}private\end{comment}",
    r"\input unbraced", r"\input{\computed}", r"\include{section}",
    r"\graphicspath{{figures/}}", r"\input{section^^2etex}",
    r"\openin1=private", r"\write18{echo bad}"])
def test_unsupported_constructs_fail_clearly(source, text):
    append_source(source, text)
    with pytest.raises(ValueError, match="unsupported|unsafe"):
        b.Sources(source).collect()


@pytest.mark.parametrize("missing", ["section.tex", "main.bbl", "references.bib"])
def test_missing_dependencies(source, missing):
    (source / "paper" / missing).unlink()
    with pytest.raises(ValueError, match="missing dependency"):
        b.Sources(source).collect()


def test_missing_graphic(source):
    append_source(source, r"\includegraphics{missing}")
    with pytest.raises(ValueError, match="missing dependency"):
        b.Sources(source).collect()


@pytest.mark.parametrize("reference", ["../../private.tex", "/tmp/private.tex", "../out/private.tex",
    ".private.tex", "dir//file.tex", "dir/./file.tex", "has space.tex", r"dir\file.tex",
    "x:private.tex", "~user/file.tex"])
def test_path_escapes_and_unsafe_names(source, reference):
    append_source(source, "\\input{" + reference + "}")
    with pytest.raises(ValueError, match="unsafe|escapes|outside public"):
        b.Sources(source).collect()


def test_symlink_is_not_a_dependency(source):
    (source / "paper/link.tex").symlink_to(source / "paper/section.tex")
    append_source(source, r"\input{link}")
    with pytest.raises(ValueError, match="symlink"):
        b.Sources(source).collect()


def test_symlink_directory_cannot_be_traversed_then_cancelled(source):
    (source / "paper/link").symlink_to(source / "paper", target_is_directory=True)
    append_source(source, r"\input{link/../section.tex}")
    with pytest.raises(ValueError, match="symlink"):
        b.Sources(source).collect()


def test_real_rebasing_and_compile_cwd_semantics(source):
    (source / "evidence").mkdir()
    (source / "evidence/value.tex").write_text("External value.\n")
    (source / "paper/evidence").mkdir()
    (source / "paper/evidence/value.tex").write_text("Distinct local value.\n")
    append_source(source, r"\input{../evidence/value}\input{evidence/value}")
    files = b.Sources(source).collect()
    assert files["evidence/value.tex"] == b"External value.\n"
    assert files["paper/evidence/value.tex"] == b"Distinct local value.\n"
    assert b"\\input{evidence/value.tex}\\input{paper/evidence/value.tex}" in files["paper/section.tex"]


@pytest.mark.parametrize("name", ["main.tex", "MAIN.tex", "main.tex/other.tex"])
def test_destination_collisions_rejected(source, name):
    sources = b.Sources(source)
    sources.collect()
    with pytest.raises(ValueError, match="collision"):
        sources.register(name, source / "paper/other.tex")


def test_cycle_is_not_silently_skipped(source):
    append_source(source, r"\input{main.tex}")
    with pytest.raises(ValueError, match="cyclic"):
        b.Sources(source).collect()


def test_only_reachable_artifacts_and_bbl_are_included(source):
    for name in ("main.pdf", "main.aux", "main.log", "notes.tex", ".env", "unused.png", "backup.tex~"):
        (source / "paper" / name).write_bytes(b"PRIVATE UNUSED")
    (source / "paper/plot.png").write_bytes(b"synthetic image")
    append_source(source, "\n% \\input{notes}\n\\includegraphics[width=2cm]{plot.png}")
    sources = b.Sources(source)
    before = (source / "paper/main.tex").read_bytes()
    files = sources.collect()
    assert set(files) == {"main.tex", "main.bbl", "paper/section.tex", "paper/plot.png"}
    assert not any(b"private" in raw or b"PRIVATE" in raw for raw in files.values())
    assert (source / "paper/main.tex").read_bytes() == before


def test_local_style_is_included_and_sanitized(source):
    path = source / "paper/main.tex"
    path.write_text("\\usepackage{local}\n" + path.read_text())
    (source / "paper/local.sty").write_text("% private style note\n\\newcommand{\\local}{OK}\n")
    assert b.Sources(source).collect()["local.sty"] == b"%\n\\newcommand{\\local}{OK}\n"


@pytest.mark.parametrize("suffix,command", [(".sty", "usepackage"), (".cls", "documentclass")])
@pytest.mark.parametrize("notice", ["Copyright 2026", "MIT License", "SPDX notice", "All rights reserved"])
def test_local_style_legal_comments_are_not_silently_stripped(source, suffix, command, notice):
    path = source / "paper/main.tex"
    path.write_text("\\" + command + "{local}\n" + path.read_text())
    style = source / "paper" / ("local" + suffix)
    raw = ("% " + notice + "\n").encode()
    style.write_bytes(raw)
    with pytest.raises(ValueError, match="legal notice requires explicit reviewed handling"):
        b.Sources(source).collect()
    assert style.read_bytes() == raw


def test_active_credential_blocks_before_compile_without_echoing_value(source, monkeypatch):
    secret = "sk-" + "9Qr7V2mX" * 5
    append_source(source, secret)
    def forbidden(*args, **kwargs):
        pytest.fail("Unsafe candidate reached compile")
    monkeypatch.setattr(b, "compile_archive", forbidden)
    with pytest.raises(ValueError, match="public scanner") as error:
        b.build(source)
    assert secret not in str(error.value)
    assert not (source / "build/arxiv.tar.gz").exists()


def test_candidate_scan_does_not_run_index_audit_and_comments_are_removed(source, monkeypatch):
    append_source(source, "\n% sk-" + "9Qr7V2mX" * 5)
    monkeypatch.setattr(b.audit_public_release, "audit_repository", lambda *a, **k: pytest.fail("full audit"))
    files = b.Sources(source).collect()
    b.scan_candidates(files)


def test_binary_dependency_receives_same_content_scan():
    with pytest.raises(ValueError, match="public scanner"):
        b.scan_candidates({"plot.png": b"synthetic binary " + b"sk-" + b"9Qr7V2mX" * 5})


@pytest.mark.parametrize("command", [r"\input{main.aux}", r"\includegraphics{main.pdf}"])
def test_explicit_build_artifacts_are_rejected(source, command):
    (source / "paper/main.pdf").write_bytes(b"%PDF")
    (source / "paper/main.aux").write_bytes(b"aux")
    append_source(source, command)
    with pytest.raises(ValueError, match="unsupported dependency|compiled source PDF"):
        b.Sources(source).collect()


def test_source_change_during_build_is_rejected(source):
    sources = b.Sources(source)
    sources.collect()
    append_source(source, "Concurrent parent edit.")
    with pytest.raises(ValueError, match="source changed"):
        sources.unchanged()


def test_archive_inventory_and_bytes(source, tmp_path):
    files = b.Sources(source).collect()
    archive = tmp_path / "bundle.tar.gz"
    b.write_archive(archive, files)
    with tarfile.open(archive) as tar:
        assert tar.getnames() == sorted(files)
        assert all(m.isfile() and m.uid == m.gid == 0 and not m.uname and not m.gname for m in tar)
    b.extract_archive(archive, tmp_path / "extracted", files)
    assert {p.relative_to(tmp_path / "extracted").as_posix(): p.read_bytes()
            for p in (tmp_path / "extracted").rglob("*") if p.is_file()} == files


@pytest.mark.parametrize("mutation", ["extra", "missing", "changed", "duplicate", "symlink", "escape", "absolute"])
def test_archive_tamper_rejected_before_extraction(tmp_path, mutation):
    archive = tmp_path / "bundle.tar.gz"
    entries = [("main.tex", b"expected", tarfile.REGTYPE)]
    if mutation == "missing":
        entries = []
    elif mutation == "changed":
        entries = [("main.tex", b"tampered", tarfile.REGTYPE)]
    elif mutation == "symlink":
        entries = [("main.tex", b"", tarfile.SYMTYPE)]
    else:
        name = {"extra": "private.txt", "duplicate": "main.tex", "escape": "../escape",
                "absolute": "/tmp/escape"}[mutation]
        entries.append((name, b"expected", tarfile.REGTYPE))
    with tarfile.open(archive, "w:gz") as tar:
        for name, raw, kind in entries:
            info = tarfile.TarInfo(name)
            info.type, info.size, info.linkname = kind, len(raw), "outside" if kind == tarfile.SYMTYPE else ""
            tar.addfile(info, io.BytesIO(raw))
    destination = tmp_path / "extracted"
    with pytest.raises(ValueError):
        b.extract_archive(archive, destination, {"main.tex": b"expected"})
    assert not destination.exists()


def test_compile_environment_does_not_inherit_user_tex_paths_or_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("TEXINPUTS", "/private/source")
    monkeypatch.setenv("SYNTHETIC_SECRET", "do-not-inherit")
    env = b.clean_environment(tmp_path / "home")
    assert env["TEXINPUTS"] == ".:"
    assert env["openin_any"] == env["openout_any"] == "p"
    assert "SYNTHETIC_SECRET" not in env


def test_recorder_rejects_unbundled_or_external_inputs(tmp_path):
    work = tmp_path / "extracted"
    work.mkdir()
    for name in ("private.tex", "../private.tex"):
        (work / "main.fls").write_text("INPUT " + name + "\n")
        with pytest.raises(ValueError, match="unbundled|outside"):
            b.check_recorded_inputs(work, {"main.tex": b""}, [])


@pytest.mark.parametrize("warning", ["There were undefined references.", "Citation `x' undefined",
    "Label(s) may have changed. Rerun to get cross-references right.", "There were multiply-defined labels."])
def test_compile_checks_actual_archive_and_final_reference_warnings(tmp_path, monkeypatch, warning):
    files = {"main.tex": b"synthetic"}
    archive = tmp_path / "bundle.tar.gz"
    b.write_archive(archive, files)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "kpsewhich":
            return subprocess.CompletedProcess(args, 0, "/system/tex\n")
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, "pdfTeX synthetic version\n")
        work = kwargs["cwd"]
        assert (work / "main.tex").read_bytes() == files["main.tex"]
        assert "-no-shell-escape" in args and "-recorder" in args
        assert kwargs["timeout"] == 300 and kwargs["stdin"] == subprocess.DEVNULL
        (work / "main.fls").write_text("INPUT ./main.tex\n")
        (work / "main.pdf").write_bytes(b"synthetic")
        (work / "main.log").write_text(warning + "\nOutput written on main.pdf (1 page)")
        return subprocess.CompletedProcess(args, 0, "")
    monkeypatch.setattr(b.subprocess, "run", run)
    with pytest.raises(ValueError, match="unresolved or unstable"):
        b.compile_archive(archive, files, tmp_path / "extracted")
    assert sum("-no-shell-escape" in args for args in calls) == 3


@pytest.mark.parametrize("changed", ["different text\f", "same text\f\f"])
def test_pdf_comparison_rejects_stale_text_or_page_count(monkeypatch, changed):
    monkeypatch.setattr(b, "pdf_text", lambda path: "same text\f" if path == "old" else changed)
    with pytest.raises(ValueError, match="PDF .*differs"):
        b.compare_pdf("old", "new", 1)


def test_pdf_comparison_normalizes_only_whitespace(monkeypatch):
    monkeypatch.setattr(b, "pdf_text", lambda p: "same\ntext\f" if p == "old" else "same text\f")
    assert b.compare_pdf("old", "new", 1) == b.digest(b"same text")


@pytest.mark.parametrize("length", [1920, 1921])
def test_abstract_limit(monkeypatch, length):
    monkeypatch.setattr(b.subprocess, "run", lambda *a, **k:
        subprocess.CompletedProcess(a, 0, "Abstract " + "a" * length + " 1 Introduction"))
    if length == 1920:
        assert len(b.plain_abstract(Path("synthetic.pdf"), r"\begin{abstract}a\end{abstract}")) == 1920
    else:
        with pytest.raises(ValueError, match="1921.*1920"):
            b.plain_abstract(Path("synthetic.pdf"), r"\begin{abstract}a\end{abstract}")


@pytest.mark.skipif(not all(shutil.which(name) for name in ("pdflatex", "pdftotext", "kpsewhich")),
                    reason="local TeX toolchain not installed")
def test_real_archive_clean_room_compile_preserves_render_and_excludes_qa_outputs(source):
    paper = source / "paper"
    for _ in range(3):
        subprocess.run(["pdflatex", "-no-shell-escape", "-halt-on-error", "-interaction=nonstopmode", "main.tex"],
                       cwd=paper, check=True, capture_output=True, timeout=60)
    original = {p: p.read_bytes() for p in paper.glob("*.tex")}
    report = b.build(source)
    assert report["verification"]["pages"] == 1
    assert report["verification"]["pdf_text_matches_current"] is True
    assert "pdfTeX" in report["verification"]["engine"]
    out = source / "build"
    assert json.loads((out / "arxiv_manifest.json").read_text()) == report
    assert (out / "arxiv_preview.pdf").is_file()
    assert (out / "arxiv_abstract.txt").read_text().strip() == "A synthetic abstract."
    with tarfile.open(out / "arxiv.tar.gz") as tar:
        assert set(tar.getnames()) == {entry["path"] for entry in report["files"]}
        assert not any(name.endswith((".aux", ".log", ".bib", ".json", ".pdf")) for name in tar.getnames())
    assert all(p.read_bytes() == raw for p, raw in original.items())
