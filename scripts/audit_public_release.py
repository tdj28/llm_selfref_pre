#!/usr/bin/env python3
"""Fail closed when the Git index is unsafe for a public release.

The audit reads blobs from the Git index, not from the working tree. This makes
its security result correspond to the content that a commit would publish while
allowing unrelated, unstaged work to remain untouched. Secret values are never
printed; findings contain only a path, line number, and rule name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator


REQUIRED_PUBLIC_FILES = frozenset(
    {
        ".gitignore",
        "AGENTS.md",
        "CITATION.cff",
        "DATA_ARTIFACTS.md",
        "LICENSE",
        "NOTICE.md",
        "docs/CLAIM_LEDGER.md",
    }
)

# The upstream AE notebook had no explicit license when reviewed. No notebook
# is currently approved for vendoring; add an explicit, reviewed path here only
# after documenting its source and license in NOTICE.md and DATA_ARTIFACTS.md.
ALLOWED_TRACKED_NOTEBOOKS: frozenset[str] = frozenset()

PRIVATE_SUFFIXES = frozenset(
    {
        ".jks",
        ".kdbx",
        ".key",
        ".keystore",
        ".ovpn",
        ".p12",
        ".pem",
        ".pfx",
        ".ppk",
        ".tfstate",
        ".tfvars",
    }
)

RESTRICTED_MODEL_SUFFIXES = frozenset(
    {".ckpt", ".gguf", ".onnx", ".pth", ".safetensors"}
)

ALLOWED_ENV_SUFFIXES = (".example", "-example", ".sample", ".template")

DIRECT_SECRET_RULES: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("private-key-header", re.compile(rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    ("openai-key", re.compile(rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b")),
    ("anthropic-key", re.compile(rb"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("huggingface-token", re.compile(rb"\bhf_[A-Za-z0-9]{20,}\b")),
    ("github-token", re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("github-fine-grained-token", re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("aws-access-key", re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    (
        "credential-in-url",
        re.compile(rb"\b[a-z][a-z0-9+.-]{2,}://[^\s/:@]+:[^\s/@]+@", re.IGNORECASE),
    ),
)

SENSITIVE_NAME = rb"(?:" + rb"|".join(
    (
        rb"ANTHROPIC_API_KEY",
        rb"AWS_SECRET_ACCESS_KEY",
        rb"GOODFIRE_API_KEY",
        rb"GITHUB_TOKEN",
        rb"HF_TOKEN",
        rb"HUGGINGFACE_TOKEN",
        rb"OPENAI_API_KEY",
        rb"RUNPOD_API_KEY",
        rb"STEERING_API_KEY",
        rb"[A-Z][A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|AUTH_TOKEN|PASSWORD|SECRET)",
    )
) + rb")"

ASSIGNMENT_RULE = re.compile(
    rb"^[ \t]*(?:export[ \t]+)?(?P<name>" + SENSITIVE_NAME + rb")"
    rb"[ \t]*=[ \t]*(?P<value>[^\r\n#]*)",
    re.IGNORECASE | re.MULTILINE,
)

QUOTED_MAPPING_RULE = re.compile(
    rb"^[ \t]*[\"']?(?P<name>" + SENSITIVE_NAME + rb")[\"']?"
    rb"[ \t]*:[ \t]*[\"'](?P<value>[^\"'\r\n]+)[\"']",
    re.IGNORECASE | re.MULTILINE,
)

PLACEHOLDER_MARKERS = (
    "...",
    "***",
    "changeme",
    "dummy",
    "example",
    "fake",
    "placeholder",
    "redact",
    "replace",
    "test-key",
    "your-",
    "your_",
)

# Exact inert value used to prove that guest attestation never retains
# non-allowlisted PID 1 environment entries. Keep this allowlist literal and
# narrow: broad markers such as ``unit`` or ``secret`` would weaken the scanner.
EXACT_TEST_PLACEHOLDERS = frozenset(
    {
        "unit-secret-that-must-never-be-retained",
    }
)


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    message: str
    line: int | None = None


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ("git", "-C", str(repo), *args),
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def index_entries(repo: Path) -> tuple[list[tuple[str, str]], list[Finding]]:
    """Return stage-zero ``(path, blob_sha)`` entries and unmerged findings."""
    result = _git(repo, "ls-files", "--stage", "-z")
    entries: list[tuple[str, str]] = []
    findings: list[Finding] = []
    for raw_entry in result.stdout.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_path = raw_entry.split(b"\t", 1)
        _mode, raw_sha, raw_stage = metadata.split(b" ", 2)
        path = raw_path.decode("utf-8", errors="surrogateescape")
        stage = raw_stage.decode("ascii")
        if stage != "0":
            findings.append(
                Finding(path, "unmerged-index-entry", "resolve this index conflict before release")
            )
            continue
        entries.append((path, raw_sha.decode("ascii")))
    return entries, findings


def iter_index_blobs(repo: Path, entries: Iterable[tuple[str, str]]) -> Iterator[tuple[str, bytes]]:
    """Stream indexed blobs through one ``git cat-file`` process."""
    process = subprocess.Popen(
        ("git", "-C", str(repo), "cat-file", "--batch"),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    try:
        for path, sha in entries:
            process.stdin.write(sha.encode("ascii") + b"\n")
            process.stdin.flush()
            header = process.stdout.readline().rstrip(b"\n").split()
            if len(header) != 3 or header[1] != b"blob":
                raise RuntimeError(f"Could not read indexed blob for {path}")
            size = int(header[2])
            data = process.stdout.read(size)
            if len(data) != size or process.stdout.read(1) != b"\n":
                raise RuntimeError(f"Truncated indexed blob for {path}")
            yield path, data
    finally:
        process.stdin.close()
        return_code = process.wait()
        if return_code:
            stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
            raise RuntimeError(f"git cat-file failed: {stderr.strip()}")


def is_allowed_placeholder(raw_value: bytes) -> bool:
    value = raw_value.decode("utf-8", errors="replace").strip().strip("\"'")
    lowered = value.lower()
    if not value or lowered in {"none", "null", "true", "false"}:
        return True
    if lowered in EXACT_TEST_PLACEHOLDERS:
        return True
    if value.startswith(("$", "<", "%", "{{")):
        return True
    if lowered.startswith(("os.environ", "os.getenv", "getenv(", "env.")):
        return True
    if lowered in {"api_key", "key", "password", "secret", "token"}:
        return True
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _line_number(data: bytes, offset: int) -> int:
    return data.count(b"\n", 0, offset) + 1


def scan_blob(path: str, data: bytes) -> list[Finding]:
    """Scan one text-like blob without returning or logging matched values."""
    if b"\0" in data[:8192]:
        return []
    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()
    for rule, pattern in DIRECT_SECRET_RULES:
        for match in pattern.finditer(data):
            if is_allowed_placeholder(match.group(0)):
                continue
            line = _line_number(data, match.start())
            if (rule, line) not in seen:
                findings.append(Finding(path, rule, "secret-like value detected", line))
                seen.add((rule, line))
    for rule_name, pattern in (
        ("secret-assignment", ASSIGNMENT_RULE),
        ("quoted-secret-mapping", QUOTED_MAPPING_RULE),
    ):
        for match in pattern.finditer(data):
            if is_allowed_placeholder(match.group("value")):
                continue
            line = _line_number(data, match.start())
            if (rule_name, line) not in seen:
                findings.append(
                    Finding(path, rule_name, "non-placeholder secret assignment detected", line)
                )
                seen.add((rule_name, line))
    return findings


def path_findings(paths: Iterable[str]) -> list[Finding]:
    findings: list[Finding] = []
    for path_string in paths:
        path = PurePosixPath(path_string)
        lowered = path_string.lower()
        basename = path.name.lower()
        suffix = path.suffix.lower()
        parts = {part.lower() for part in path.parts}

        if basename == "checkpoint.md":
            findings.append(
                Finding(path_string, "private-continuity-file", "checkpoint.md must remain ignored")
            )
        if basename == ".env" or (
            basename.startswith(".env.") and not basename.endswith(ALLOWED_ENV_SUFFIXES)
        ):
            findings.append(Finding(path_string, "environment-file", "environment files must remain ignored"))
        if suffix in PRIVATE_SUFFIXES or basename.startswith(
            ("id_dsa", "id_ecdsa", "id_ed25519", "id_rsa")
        ):
            findings.append(Finding(path_string, "private-key-file", "private key material cannot be tracked"))
        if re.search(r"(^|/)annotation_key.*_private\.csv(?:\.sha256)?$", lowered):
            findings.append(Finding(path_string, "private-annotation-key", "private linkage keys cannot be tracked"))
        if re.search(r"(^|/)coder_[^/]*\.csv$", lowered):
            findings.append(Finding(path_string, "private-coder-file", "coder response files cannot be tracked"))
        if basename in {
            ".netrc",
            ".npmrc",
            ".pypirc",
            "credentials.json",
            "secrets.json",
            "secrets.toml",
            "secrets.yaml",
            "secrets.yml",
            "token.json",
        } or parts.intersection({".aws", ".azure", ".ssh", ".secrets"}):
            findings.append(Finding(path_string, "credential-file", "credential stores cannot be tracked"))
        if suffix == ".ipynb" and path_string not in ALLOWED_TRACKED_NOTEBOOKS:
            findings.append(
                Finding(
                    path_string,
                    "unreviewed-notebook",
                    "notebook source requires explicit license and provenance review",
                )
            )
        if suffix in RESTRICTED_MODEL_SUFFIXES:
            findings.append(
                Finding(path_string, "restricted-model-artifact", "model weights cannot be tracked")
            )
    return findings


def ignored_private_file_findings(repo: Path) -> list[Finding]:
    candidates = [repo / ".env", repo / "checkpoint.md", repo / "steering" / ".env"]
    candidates.extend(repo.glob("data/**/annotation_key*_private.csv*"))
    candidates.extend(repo.glob("data/**/coder_*.csv"))
    candidates.extend(repo.glob("tmp/**/coder_*.csv"))

    findings: list[Finding] = []
    for candidate in sorted({path for path in candidates if path.exists()}):
        relative = candidate.relative_to(repo).as_posix()
        result = _git(repo, "check-ignore", "-q", "--", relative, check=False)
        if result.returncode != 0:
            findings.append(
                Finding(relative, "private-file-not-ignored", "local private file is not covered by .gitignore")
            )
    return findings


def whitespace_findings(repo: Path) -> list[Finding]:
    findings: list[Finding] = []
    for label, args in (
        ("working-tree-whitespace", ("diff", "--check")),
        ("index-whitespace", ("diff", "--cached", "--check")),
    ):
        result = _git(repo, *args, check=False)
        if result.returncode:
            findings.append(
                Finding("<repository>", label, "git diff --check reported whitespace errors")
            )
    return findings


def release_manifest_findings(
    manifests: dict[str, bytes], blob_records: dict[str, tuple[int, str]]
) -> tuple[list[Finding], int]:
    """Verify manifest-listed byte counts and hashes against indexed blobs."""
    findings: list[Finding] = []
    verified_entries = 0
    for manifest_path, raw_manifest in sorted(manifests.items()):
        try:
            manifest = json.loads(raw_manifest)
        except (UnicodeDecodeError, json.JSONDecodeError):
            findings.append(
                Finding(manifest_path, "invalid-release-manifest", "release manifest is not valid JSON")
            )
            continue
        files = manifest.get("files") if isinstance(manifest, dict) else None
        if not isinstance(files, list):
            findings.append(
                Finding(manifest_path, "invalid-release-manifest", "release manifest has no files list")
            )
            continue
        base = PurePosixPath(manifest_path).parent
        for index, item in enumerate(files):
            if not isinstance(item, dict) or not {"path", "bytes", "sha256"}.issubset(item):
                findings.append(
                    Finding(
                        manifest_path,
                        "invalid-release-entry",
                        f"release file entry {index} lacks path, bytes, or sha256",
                    )
                )
                continue
            relative = PurePosixPath(str(item["path"]))
            if relative.is_absolute() or ".." in relative.parts:
                findings.append(
                    Finding(
                        manifest_path,
                        "unsafe-release-path",
                        f"release file entry {index} escapes its release directory",
                    )
                )
                continue
            indexed_path = (base / relative).as_posix()
            record = blob_records.get(indexed_path)
            if record is None:
                findings.append(
                    Finding(
                        indexed_path,
                        "untracked-release-file",
                        f"file listed by {manifest_path} is absent from the Git index",
                    )
                )
                continue
            actual_bytes, actual_sha = record
            if actual_bytes != int(item["bytes"]):
                findings.append(
                    Finding(
                        indexed_path,
                        "release-byte-mismatch",
                        f"indexed byte count differs from {manifest_path}",
                    )
                )
            if actual_sha != str(item["sha256"]):
                findings.append(
                    Finding(
                        indexed_path,
                        "release-hash-mismatch",
                        f"indexed SHA-256 differs from {manifest_path}",
                    )
                )
            if actual_bytes == int(item["bytes"]) and actual_sha == str(item["sha256"]):
                verified_entries += 1
    return findings, verified_entries


def audit_repository(repo: Path) -> dict[str, object]:
    repo = repo.resolve()
    entries, findings = index_entries(repo)
    paths = [path for path, _sha in entries]
    findings.extend(path_findings(paths))

    missing = sorted(REQUIRED_PUBLIC_FILES.difference(paths))
    findings.extend(
        Finding(path, "missing-public-provenance", "required public provenance file is absent")
        for path in missing
    )

    scanned_bytes = 0
    blob_records: dict[str, tuple[int, str]] = {}
    release_manifests: dict[str, bytes] = {}
    for path, data in iter_index_blobs(repo, entries):
        scanned_bytes += len(data)
        blob_records[path] = (len(data), hashlib.sha256(data).hexdigest())
        if path.endswith("/release_manifest.json") or path.endswith("/MANIFEST.json"):
            release_manifests[path] = data
        findings.extend(scan_blob(path, data))

    manifest_findings, verified_release_entries = release_manifest_findings(
        release_manifests, blob_records
    )
    findings.extend(manifest_findings)
    findings.extend(ignored_private_file_findings(repo))
    findings.extend(whitespace_findings(repo))
    findings = sorted(findings, key=lambda row: (row.path, row.line or 0, row.rule))
    return {
        "status": "pass" if not findings else "fail",
        "scope": "git-index-plus-private-ignore-and-whitespace-checks",
        "tracked_files_scanned": len(entries),
        "tracked_bytes_scanned": scanned_bytes,
        "release_manifests_verified": len(release_manifests),
        "release_entries_verified": verified_release_entries,
        "required_public_files": sorted(REQUIRED_PUBLIC_FILES),
        "findings": [asdict(finding) for finding in findings],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = audit_repository(args.repo)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"Public release audit: {str(report['status']).upper()} "
            f"({report['tracked_files_scanned']} indexed files, "
            f"{report['tracked_bytes_scanned']} bytes)"
        )
        for finding in report["findings"]:
            line = f":{finding['line']}" if finding["line"] is not None else ""
            print(f"- {finding['path']}{line} [{finding['rule']}] {finding['message']}")
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
