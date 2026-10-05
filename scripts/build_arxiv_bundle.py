#!/usr/bin/env python3
"""Build and locally test this paper's dependency-only arXiv source archive.

Run make paper first for current main.pdf/main.bbl. Supports literal braced
input/includegraphics, local styles, and one standard BibTeX bibliography;
dynamic file references and catcode/verbatim parsing are deliberately unsupported.
Only bundle copies are sanitized. Empty comment markers retain TeX's newline
suppression. Submission 1.5 uses an uploaded .bbl when present and compiles from
the upload root: https://info.arxiv.org/help/submit_tex.html .
The actual tar is checked, extracted and compiled without shell escape. The local
engine need not match arXiv's; submission preview remains necessary. The preview
PDF, abstract and hash/verification report stay outside the upload directory.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

if __package__:
    from . import audit_public_release
else:
    import audit_public_release

ROOT = Path(__file__).resolve().parents[1]
ABSTRACT_LIMIT = 1920
COMMAND = re.compile(r"\\([A-Za-z@]+|[^\r\n])|%[^\r\n]*")
ARGUMENT = re.compile(r"\s*(?:\[([^\[\]]*)\]\s*)?\{([^{}]*)\}")
COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
UNSUPPORTED = {
    "include", "includeonly", "graphicspath", "DeclareGraphicsExtensions",
    "import", "subimport", "subfile", "externaldocument", "InputIfFileExists",
    "IfFileExists", "verbatiminput", "VerbatimInput", "lstinputlisting",
    "addbibresource", "printbibliography", "catcode", "endlinechar",
    "obeylines", "obeyspaces", "verb", "Verb", "lstinline", "mintinline",
    "openin", "openout", "read", "readline", "write", "pdfximage",
    "scantokens", "input@path",
}
ASCII = {"\u2212": "-", "\u2013": "--", "\u2014": "---", "\u2018": "'", "\u2019": "'",
         "\u201c": '"', "\u201d": '"', "\ufb01": "fi", "\ufb02": "fl"}


def require(condition, message):
    if not condition:
        raise ValueError("arXiv bundle failed: " + message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sanitize(text):
    """Strip comment contents, not the % or line ending (including at EOF)."""
    clean = COMMAND.sub(lambda m: "%" if m.group().startswith("%") else m.group(), text)
    require("^^" not in clean, "unsupported TeX ^^ character notation")
    for match in COMMAND.finditer(clean):
        command = match.group(1)
        require(command not in UNSUPPORTED, "unsupported TeX command " + str(command))
        if command == "begin":
            arg = ARGUMENT.match(clean, match.end())
            require(not arg or arg.group(2) not in {
                "verbatim", "verbatim*", "Verbatim", "lstlisting", "minted",
                "comment", "filecontents", "filecontents*"},
                "unsupported literal/comment/file-writing environment")
    return clean


def safe_name(name):
    path = PurePosixPath(name)
    require(bool(name) and not path.is_absolute() and path.as_posix() == name
            and all(COMPONENT.fullmatch(part) for part in path.parts),
            "unsafe bundle filename " + repr(name))
    return name


class Sources:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.paper = self.root / "paper"
        self.files = {}
        self.origins = {}
        self.raw = {}
        self.names = {}
        self.active = set()
        self.bibliographies = 0

    def resolve(self, reference, suffixes):
        # TeX resolves paths from the compilation cwd, not the input's directory.
        # Walk .. explicitly: never discard it or traverse links.
        require(reference and not reference.startswith("/"), "unsafe source path " + repr(reference))
        require(not self.paper.is_symlink(), "symlink paper directory")
        parts = ["paper"]
        for part in reference.split("/"):
            if part == "..":
                require(bool(parts), "source path escapes repository")
                parts.pop()
            else:
                require(COMPONENT.fullmatch(part), "unsafe source path " + repr(reference))
                parts.append(part)
            require(not self.root.joinpath(*parts).is_symlink(), "symlink in source path")
        require(parts and parts[0] in {"paper", "evidence", "data"},
                "source outside public manuscript/evidence trees")
        source = self.root.joinpath(*parts)
        candidates = [source] if source.suffix else [source.with_suffix(s) for s in suffixes]
        for candidate in candidates:
            require(not candidate.is_symlink(), "symlink source " + reference)
            if candidate.is_file():
                require(candidate.suffix in suffixes, "unsupported dependency type " + reference)
                return candidate
        raise ValueError("arXiv bundle failed: missing dependency " + reference)

    def read(self, source):
        raw = source.read_bytes()
        require(source not in self.raw or self.raw[source] == raw, "source changed during collection")
        self.raw[source] = raw
        return raw

    def register(self, name, source):
        safe_name(name)
        for i in range(1, len(PurePosixPath(name).parts) + 1):
            prefix = PurePosixPath(*PurePosixPath(name).parts[:i]).as_posix()
            require(self.names.get(prefix.casefold(), prefix) == prefix, "case-folded filename collision")
            self.names[prefix.casefold()] = prefix
        require(name not in self.origins or self.origins[name] == source, "destination collision: " + name)
        require(not any(name.startswith(n + "/") or n.startswith(name + "/") for n in self.origins),
                "file/directory destination collision: " + name)
        self.origins[name] = source

    def add(self, source, name=None):
        name = name or source.relative_to(self.root).as_posix()
        self.register(name, source)
        require(source not in self.active, "cyclic TeX input " + name)
        if name in self.files:
            return name
        raw = self.read(source)
        if source.suffix in {".pdf", ".png", ".jpg"}:
            require(source.name.lower() != "main.pdf" and not source.with_suffix(".tex").exists(),
                    "compiled source PDF is not a figure dependency: " + name)
            self.files[name] = raw
            return name
        self.active.add(source)
        text = raw.decode("utf-8")
        if source.suffix in {".sty", ".cls"}:
            require(not re.search(r"copyright|licen[cs]e|SPDX|all rights reserved", text, re.I),
                    "local style/class legal notice requires explicit reviewed handling")
        text = sanitize(text)
        edits = []
        for match in COMMAND.finditer(text):
            command = match.group(1)
            if command not in {"input", "includegraphics", "usepackage", "RequirePackage",
                               "documentclass", "LoadClass", "bibliography", "bibliographystyle"}:
                continue
            arg = ARGUMENT.match(text, match.end())
            require(arg is not None, "unsupported argument to " + str(command) + " in " + name)
            value = arg.group(2)
            if command in {"input", "bibliography", "bibliographystyle"}:
                require(arg.group(1) is None, "unsupported options for " + command)
            if command in {"input", "includegraphics"}:
                suffixes = (".tex",) if command == "input" else (".pdf", ".png", ".jpg")
                dependency = self.resolve(value, suffixes)
                target = self.add(dependency)
                edits.append((arg.start(2), arg.end(2), target))
            elif command == "bibliography":
                self.bibliographies += 1
                for database in value.split(","):
                    require("/" not in database, "unsupported bibliography path")
                    self.read(self.resolve(database, (".bib",)))
            else:
                suffix = ".cls" if command in {"documentclass", "LoadClass"} else ".sty"
                for package in value.split(","):
                    require(COMPONENT.fullmatch(package), "unsupported package/style name")
                    if command == "bibliographystyle":
                        continue  # BibTeX already produced main.bbl; no .bst needed.
                    local = self.paper / (package + suffix)
                    if local.exists() or local.is_symlink():
                        self.add(self.resolve(package + suffix, (suffix,)), package + suffix)
        for start, end, replacement in reversed(edits):
            text = text[:start] + replacement + text[end:]
        self.files[name] = text.encode("utf-8")
        self.active.remove(source)
        return name

    def collect(self):
        self.add(self.resolve("main.tex", (".tex",)), "main.tex")
        require(self.bibliographies == 1, "expected one standard BibTeX bibliography")
        self.add(self.resolve("main.bbl", (".bbl",)), "main.bbl")
        return self.files

    def unchanged(self):
        for path, raw in self.raw.items():
            require(path.read_bytes() == raw, "source changed during build: " + path.relative_to(self.root).as_posix())


def write_archive(archive, files):
    with tarfile.open(archive, "w:gz", format=tarfile.USTAR_FORMAT) as tar:
        for name, raw in sorted(files.items()):
            safe_name(name)
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(raw), 0o644
            tar.addfile(info, io.BytesIO(raw))


def scan_candidates(files):
    for name, raw in files.items():
        findings = audit_public_release.scan_blob(name, raw)
        require(not findings, "candidate content rejected by public scanner: "
                + ", ".join(sorted({finding.rule for finding in findings})))


def extract_archive(archive, destination, expected):
    """No extractall: accept only exact regular-file members, before any write."""
    members = {}
    folded = set()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            name = safe_name(member.name)
            require(member.isfile() and name not in members and name.casefold() not in folded,
                    "nonregular or duplicate archive member " + name)
            require(name in expected and member.size == len(expected[name]), "unexpected archive member " + name)
            raw = tar.extractfile(member).read()
            require(raw == expected[name], "archive bytes differ: " + name)
            members[name] = raw
            folded.add(name.casefold())
    require(members.keys() == expected.keys(), "archive inventory differs")
    require(not destination.exists(), "extraction directory must be new")
    destination.mkdir()
    for name, raw in members.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)


def clean_environment(home):
    home.mkdir()
    return {"PATH": os.defpath + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(home), "TMPDIR": str(home), "LC_ALL": "C", "TZ": "UTC",
            "TEXMFHOME": str(home), "TEXMFCONFIG": str(home / "config"),
            "TEXMFVAR": str(home / "var"), "TEXINPUTS": ".:",
            "openin_any": "p", "openout_any": "p"}


def check_recorded_inputs(work, files, system_roots):
    work = work.resolve()
    generated = {"main.aux", "main.out", "main.toc", "main.lof", "main.lot"}
    for line in (work / "main.fls").read_text().splitlines():
        if not line.startswith("INPUT "):
            continue
        path = (work / line[6:]).resolve()
        if path.is_relative_to(work):
            require(path.relative_to(work).as_posix() in files.keys() | generated,
                    "unbundled local TeX input")
        else:
            require(any(path.is_relative_to(root) for root in system_roots),
                    "TeX read outside archive/system installation")


def compile_archive(archive, files, destination):
    extract_archive(archive, destination, files)
    env = clean_environment(destination.parent / "tex-home")
    system_roots = []
    for variable in ("TEXMFROOT", "TEXMFLOCAL", "TEXMFDIST", "TEXMFSYSVAR", "TEXMFSYSCONFIG"):
        result = subprocess.run(["kpsewhich", "-var-value=" + variable], env=env,
                                capture_output=True, text=True, check=True, timeout=30)
        path = Path(result.stdout.strip())
        require(path.is_absolute() and path != Path("/"), "cannot establish system TeX tree")
        system_roots.append(path.resolve())
    engine = subprocess.run(["pdflatex", "--version"], env=env, capture_output=True,
                            text=True, check=True, timeout=30).stdout.splitlines()[0]
    for _ in range(3):
        run = subprocess.run(["pdflatex", "-no-shell-escape", "-recorder", "-interaction=nonstopmode",
                              "-halt-on-error", "-file-line-error", "main.tex"], cwd=destination,
                             env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
        require(run.returncode == 0, "extracted-archive pdflatex failed:\n" + run.stdout[-3000:])
        check_recorded_inputs(destination, files, system_roots)
    log = (destination / "main.log").read_text(errors="replace")
    require(not re.search(r"undefined (references|citations)|(?:Reference|Citation).*undefined|"
                          r"Label\(s\) may have changed|Rerun to get|multiply[- ]defined", log, re.I),
            "unresolved or unstable references/citations in extracted archive")
    pages = re.search(r"Output written on main\.pdf \((\d+) pages?", log)
    require(pages is not None and (destination / "main.pdf").is_file(), "no PDF produced")
    return int(pages.group(1)), engine


def pdf_text(pdf):
    return subprocess.run(["pdftotext", str(pdf), "-"], check=True, capture_output=True,
                          text=True, timeout=30).stdout


def compare_pdf(reference, compiled, pages):
    original, rebuilt = pdf_text(reference), pdf_text(compiled)
    require(original.count("\f") == rebuilt.count("\f") == pages,
            "archive/current paper PDF page count differs; run make paper")
    normalized = [re.sub(r"\s+", " ", text).strip() for text in (original, rebuilt)]
    require(normalized[0] == normalized[1], "archive/current paper PDF text differs; run make paper or inspect sanitization")
    return digest(normalized[0].encode("utf-8"))


def plain_abstract(pdf, source):
    page = subprocess.run(["pdftotext", "-f", "1", "-l", "1", str(pdf), "-"],
                          check=True, capture_output=True, text=True, timeout=30).stdout
    flat = re.sub(r"\s+", " ", page)
    start, end = flat.find("Abstract "), flat.find(" 1 Introduction")
    require(0 <= start < end, "abstract boundaries not found in compiled main.pdf")
    text = flat[start + len("Abstract "):end].strip()
    abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", source, re.S)
    require(abstract is not None, "abstract source not found")
    for word in set(re.findall(r"\b[A-Za-z]+(?:-[A-Za-z]+)+\b", abstract.group(1))):
        text = re.sub(r"\b" + word.replace("-", "") + r"\b", word, text)
    for char, replacement in ASCII.items():
        text = text.replace(char, replacement)
    require(text.isascii(), "non-ASCII character left in abstract")
    require(len(text) <= ABSTRACT_LIMIT, f"abstract is {len(text)} characters (limit {ABSTRACT_LIMIT})")
    return text


def build(root=ROOT):
    root = Path(root).resolve()
    sources = Sources(root)
    files = sources.collect()
    scan_candidates(files)
    reference_pdf = sources.read(sources.resolve("main.pdf", (".pdf",)))
    out = root / "build"
    require(not out.is_symlink(), "symlink build directory")
    out.mkdir(exist_ok=True)
    # Publish nothing new until the actual archived bytes pass all checks.
    with tempfile.TemporaryDirectory(prefix="arxiv-check-") as temporary:
        temporary = Path(temporary)
        reference = temporary / "reference.pdf"
        reference.write_bytes(reference_pdf)
        archive = temporary / "arxiv.tar.gz"
        write_archive(archive, files)
        work = temporary / "extracted"
        pages, engine = compile_archive(archive, files, work)
        text_sha = compare_pdf(reference, work / "main.pdf", pages)
        abstract = plain_abstract(work / "main.pdf", files["main.tex"].decode("utf-8"))
        sources.unchanged()
        report = {"schema": "arxiv_bundle_v1", "archive_sha256": digest(archive.read_bytes()),
                  "files": [{"path": name, "bytes": len(raw), "sha256": digest(raw),
                             "source": sources.origins[name].relative_to(root).as_posix(),
                             "source_sha256": digest(sources.raw[sources.origins[name]])}
                            for name, raw in sorted(files.items())],
                  "verification": {"extracted_archive": True, "shell_escape": False,
                                   "candidate_content_scan": "pass",
                                   "references_resolved": True, "pages": pages, "engine": engine,
                                   "pdf_text_matches_current": True, "normalized_text_sha256": text_sha,
                                   "current_pdf_sha256": digest(reference_pdf),
                                   "preview_pdf_sha256": digest((work / "main.pdf").read_bytes()),
                                   "abstract_characters": len(abstract),
                                   "scope": "local engine only; arXiv submission preview still required"},
                  "bibliography": "compiled main.bbl; source databases excluded"}
        upload = out / "arxiv"
        outputs = ["arxiv.tar.gz", "arxiv_manifest.json", "arxiv_abstract.txt", "arxiv_preview.pdf"]
        require(not any(path.is_symlink() for path in [upload, *(out / name for name in outputs)]),
                "symlink output destination")
        if upload.exists():
            shutil.rmtree(upload)
        extract_archive(archive, upload, files)
        shutil.copyfile(archive, out / "arxiv.tar.gz")
        shutil.copyfile(work / "main.pdf", out / "arxiv_preview.pdf")
        (out / "arxiv_abstract.txt").write_text(abstract + "\n")
        (out / "arxiv_manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    try:
        report = build()
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    checked = report["verification"]
    print(f"Bundle: {len(report['files'])} files; extracted archive compiled to {checked['pages']} pages")
    print("Archive: build/arxiv.tar.gz; report: build/arxiv_manifest.json; preview: build/arxiv_preview.pdf")
    print(f"Abstract: build/arxiv_abstract.txt ({checked['abstract_characters']} characters)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
