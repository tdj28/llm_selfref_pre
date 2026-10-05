#!/usr/bin/env python3
"""Assemble a self-contained arXiv source bundle for paper/main.tex.

Copies the manuscript, every \\input file and graphic it reaches (including
../evidence and ../data dependencies) into build/arxiv/, rewrites
parent-directory paths to bundle-local ones, adds the BibTeX output, writes
the plain-text abstract for the submission form (failing above arXiv's
1,920-character limit), test-compiles a copy outside the repository with
pdflatex alone, as arXiv does, and packs build/arxiv.tar.gz.
Run `make paper` first so main.bbl and main.pdf are current.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
OUT = ROOT / "build" / "arxiv"
ABSTRACT_LIMIT = 1920
INPUT = re.compile(r"\\input\{([^}]+)\}")
GRAPHIC = re.compile(r"(\\includegraphics(?:\[[^\]]*\])?\{)([^}]+)(\})")
ASCII = {"\u2212": "-", "\u2013": "--", "\u2014": "---", "\u2018": "'", "\u2019": "'",
         "\u201c": '"', "\u201d": '"', "\ufb01": "fi", "\ufb02": "fl"}


def require(condition, message):
    if not condition:
        raise SystemExit("arXiv bundle failed: " + message)


def local_name(reference: str) -> str:
    """Bundle-relative path for a reference written relative to paper/."""
    path = PurePosixPath(reference)
    parts = [p for p in path.parts if p != ".."]
    require(parts and not path.is_absolute(), "unsupported path " + reference)
    return str(PurePosixPath(*parts))


def resolve(reference: str, suffixes) -> Path:
    source = (PAPER / reference).resolve()
    if source.suffix:
        require(source.is_file(), "missing file " + reference)
        return source
    for suffix in suffixes:
        if source.with_suffix(suffix).is_file():
            return source.with_suffix(suffix)
    raise SystemExit("arXiv bundle failed: missing file " + reference)


def copy_tex(reference: str, seen: set[str]):
    source = resolve(reference, (".tex",))
    target = local_name(reference if reference.endswith(".tex") else reference + ".tex")
    if target in seen:
        return
    seen.add(target)
    text = source.read_text()
    for match in INPUT.finditer(text):
        copy_tex(match.group(1), seen)
    for match in GRAPHIC.finditer(text):
        graphic = resolve(match.group(2), (".pdf", ".png", ".jpg"))
        destination = OUT / local_name(match.group(2))
        if not destination.suffix:
            destination = destination.with_suffix(graphic.suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(graphic, destination)
    text = INPUT.sub(lambda m: r"\input{" + local_name(m.group(1)) + "}", text)
    text = GRAPHIC.sub(lambda m: m.group(1) + local_name(m.group(2)) + m.group(3), text)
    destination = OUT / target
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text)


def plain_abstract() -> str:
    pdf = PAPER / "main.pdf"
    require(pdf.is_file(), "paper/main.pdf missing; run make paper")
    page = subprocess.run(["pdftotext", "-f", "1", "-l", "1", str(pdf), "-"],
                          check=True, capture_output=True, text=True).stdout
    flat = re.sub(r"\s+", " ", page)
    start, end = flat.find("Abstract "), flat.find(" 1 Introduction")
    require(0 <= start < end, "abstract boundaries not found in main.pdf")
    text = flat[start + len("Abstract "):end].strip()
    source = (PAPER / "main.tex").read_text().split(r"\begin{abstract}")[1].split(r"\end{abstract}")[0]
    for word in set(re.findall(r"\b[A-Za-z]+(?:-[A-Za-z]+)+\b", source)):
        text = re.sub(r"\b" + word.replace("-", "") + r"\b", word, text)
    for char, replacement in ASCII.items():
        text = text.replace(char, replacement)
    require(text.isascii(), "non-ASCII character left in abstract")
    require(len(text) <= ABSTRACT_LIMIT, f"abstract is {len(text)} characters (limit {ABSTRACT_LIMIT})")
    return text


def test_compile():
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "arxiv"
        shutil.copytree(OUT, work)
        for _ in range(3):
            run = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
                                 cwd=work, capture_output=True, text=True)
            require(run.returncode == 0, "standalone pdflatex failed; see main.log in a manual rerun")
        log = (work / "main.log").read_text(errors="replace")
        require("There were undefined references" not in log, "unresolved references in standalone build")
        require(not re.search(r"LaTeX Warning: (Reference|Citation) .* undefined", log),
                "undefined reference or citation in standalone build")
        pages = re.search(r"Output written on main\.pdf \((\d+) pages", log)
        require(pages is not None, "no PDF produced")
        return int(pages.group(1))


def main():
    for name in ("main.bbl", "main.pdf"):
        require((PAPER / name).is_file(), f"paper/{name} missing; run make paper")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    seen: set[str] = set()
    copy_tex("main.tex", seen)
    for name in ("main.bbl", "references.bib"):
        shutil.copy2(PAPER / name, OUT / name)
    leftover = [str(p.relative_to(OUT)) for p in OUT.rglob("*.tex")
                if re.search(r"\\(input|includegraphics)(\[[^\]]*\])?\{\.\./", p.read_text())]
    require(not leftover, "parent paths remain in " + ", ".join(leftover))
    abstract = plain_abstract()
    (OUT.parent / "arxiv_abstract.txt").write_text(abstract + "\n")
    pages = test_compile()
    archive = OUT.parent / "arxiv.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(OUT.rglob("*")):
            if path.is_file():
                tar.add(path, arcname=str(path.relative_to(OUT)))
    files = sum(1 for p in OUT.rglob("*") if p.is_file())
    print(f"Bundle: {files} files in build/arxiv ({len(seen)} TeX files); standalone build {pages} pages")
    print(f"Archive: build/arxiv.tar.gz; abstract for the form: build/arxiv_abstract.txt ({len(abstract)} characters)")


if __name__ == "__main__":
    sys.exit(main())
