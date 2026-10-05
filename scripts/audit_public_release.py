#!/usr/bin/env python3
"""Fail closed when the Git index is unsafe for a public release.

The audit reads blobs from the Git index, not from the working tree. This makes
its security result correspond to the content that a commit would publish while
allowing unrelated, unstaged work to remain untouched. Secret values are never
printed; findings contain only a path, line number, and rule name.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import subprocess
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator

if __package__:
    from . import audit_sae_residual_release as residual_audit
    from . import audit_sae_exposure_release as exposure_audit
else:
    import audit_sae_residual_release as residual_audit
    import audit_sae_exposure_release as exposure_audit


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

# These evidence copies describe the canonical data releases, not local rows.
# Accept an alias only when its indexed bytes match the indexed source below.
RELEASE_MANIFEST_ALIASES = {
    "evidence/source_alignment/RELEASE_MANIFEST.json":
        "data/berg_source_replication/source_aligned_v1_20261001/RELEASE_MANIFEST.json",
    "evidence/ensemble_alignment/RELEASE_MANIFEST.json":
        "data/berg_ensemble_replication/random_subset_v1_20261001/RELEASE_MANIFEST.json",
}

# Preserve upstream legal text verbatim; it still receives the secret scan.
PRESERVED_SOURCE_BYTES = {
    "data/operator_matching/calibration_v1_20261003/LLAMA_3_3_LICENSE.txt":
        "fb58d9a630ccc1dc0d08f8c00232de56bc73309020f59c8181d0c12ef28d9f8c",
}
HASH_MAP_MANIFESTS = {
    "data/operator_matching/calibration_v1_20261003/RELEASE_MANIFEST.json":
        "operator_matching_release_v1",
    "data/operator_matching/fine_v1_20261003/RELEASE_MANIFEST.json":
        "operator_matching_fine_release_v1",
}

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
        rb"OSF_TOKEN",
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
    rb"(?:^|[\{,])[ \t]*[\"']?(?P<name>" + SENSITIVE_NAME + rb")[\"']?"
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


def index_entries(
    repo: Path, *, modes: dict[str, str] | None = None
) -> tuple[list[tuple[str, str]], list[Finding]]:
    """Return stage-zero ``(path, blob_sha)`` entries and unmerged findings."""
    result = _git(repo, "ls-files", "--stage", "-z")
    entries: list[tuple[str, str]] = []
    findings: list[Finding] = []
    for raw_entry in result.stdout.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_path = raw_entry.split(b"\t", 1)
        raw_mode, raw_sha, raw_stage = metadata.split(b" ", 2)
        path = raw_path.decode("utf-8", errors="surrogateescape")
        stage = raw_stage.decode("ascii")
        if stage != "0":
            findings.append(
                Finding(path, "unmerged-index-entry", "resolve this index conflict before release")
            )
            continue
        entries.append((path, raw_sha.decode("ascii")))
        if modes is not None:
            modes[path] = raw_mode.decode("ascii")
    return entries, findings


def residual_size_preflight(
    repo: Path, entries: Iterable[tuple[str, str]]
) -> tuple[set[str], list[Finding]]:
    """Reject oversized safetensors without materializing model-sized blobs."""
    candidates = [(path, sha) for path, sha in entries if path.lower().endswith(".safetensors")]
    if not candidates:
        return set(), []
    result = subprocess.run(
        ("git", "-C", str(repo), "cat-file", "--batch-check"),
        input=b"".join(sha.encode("ascii") + b"\n" for _, sha in candidates),
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    headers = result.stdout.splitlines()
    if len(headers) != len(candidates):
        raise RuntimeError("Unexpected indexed object size response")
    blocked, findings = set(), []
    for (path, sha), raw_header in zip(candidates, headers):
        header = raw_header.split()
        valid = (len(header) == 3 and header[0] == sha.encode("ascii")
                 and header[1] == b"blob" and header[2].isdigit())
        limit = exposure_audit.capture_size_limit(path) or residual_audit.MAX_CAPTURE_BYTES
        if not valid or int(header[2]) > limit:
            blocked.add(path)
            findings.append(Finding(path, "residual-blob-size-limit",
                                    "safetensors is not a bounded activation-capture blob"))
    return blocked, findings


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
        process.stdout.close()
        return_code = process.wait()
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        if process.stderr:
            process.stderr.close()
        if return_code:
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


MAX_DECOMPRESSED_BYTES = 128 * 1024 * 1024


def is_release_manifest(path: str) -> bool:
    name = PurePosixPath(path).name
    # Lowercase manifest.json is also used for runtime metadata, not file hashes.
    return name.lower() == "release_manifest.json" or name == "MANIFEST.json"


def scan_blob(path: str, data: bytes) -> list[Finding]:
    """Scan bytes and bounded gzip payloads; never echo matched secret values."""
    if path.lower().endswith(".gz") or data.startswith(b"\x1f\x8b"):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                expanded = stream.read(MAX_DECOMPRESSED_BYTES + 1)
        except (OSError, EOFError, zlib.error):
            return [Finding(path, "invalid-compressed-file", "gzip content cannot be scanned")]
        if len(expanded) > MAX_DECOMPRESSED_BYTES:
            return [Finding(path, "compressed-scan-limit", "expanded gzip exceeds the scan limit")]
        # Do not recurse: nested compression is outside this bounded log scan.
        if expanded.startswith(b"\x1f\x8b"):
            return [Finding(path, "nested-compressed-file", "nested gzip requires explicit review")]
        return scan_bytes(path, expanded)
    return scan_bytes(path, data)


# Reviewed 2026-10-02: event 725, data.raw.output[0].encrypted_content in
# the completed frontier journal. Random ciphertext matches the token regex.
# Bind the entire blob AND exact match; no general encrypted-field exemption.
# See docs/FRONTIER_BILINGUAL_RELEASE_AUDIT_20261002.md.
REVIEWED_CIPHERTEXT_MATCHES = {
    ("openai-key", 5083198, 5084681,
     "6a8f38f1792dd3417355f4297f2e9dab1524bf2bdd2a75cd2cbc85425fb0aae0"):
        "923b93b3b4e699e55878295c114de3df6bda3d624763494abe53d51497bc4925",
    # Reviewed 2026-10-04: OpenRouter event 2879, reasoning.encrypted metadata.
    # Exact binding and credential comparison: data/openrouter_swap/README.md.
    ("openai-key", 16062128, 16064780,
     "691d78ab917852ea46bfe5b9aa349fd1d8c9b6b27a9e60d521cbf5443cb7435d"):
        "09a4cce440870d101b2abeeec85e0b75ff31f8d2244e9c98f2a80710fff4a244",
    # Reviewed 2026-10-05: Kolibri judge event 728, reasoning.encrypted metadata.
    # Raw response, final journal, and the exporter's two decoded JSON forms.
    # Six known credentials matched none of 9,585 raw/decoded representations.
    # Each entry remains bound to its whole blob and exact match position/hash.
    ("openai-key", 2195, 4378,
     "5b41f973d0f5a6c58a53803e0011468d817392f474c4e266c9b17dbb93657625"):
        "c61bb99830e181da1aed8baa1a5189ef3bce3b52e4986465da3c80f520f545f5",
    ("openai-key", 3468727, 3470910,
     "5b41f973d0f5a6c58a53803e0011468d817392f474c4e266c9b17dbb93657625"):
        "9a3c4a19359b38f934c2d827d631141d200a0d5b2ad9a786a68b8c8c43f9ac26",
    ("openai-key", 2198, 4381,
     "5b41f973d0f5a6c58a53803e0011468d817392f474c4e266c9b17dbb93657625"):
        "e64d68d2a1856a1e5433c56552051cc4209460cce1b25748a8ca12e33d542560",
    ("openai-key", 2090, 4273,
     "5b41f973d0f5a6c58a53803e0011468d817392f474c4e266c9b17dbb93657625"):
        "889e6244fdf47fe6153f34981f5ece0448431da72e158c6a410cad09314e332d",
}


def _reviewed_ciphertext_match(data: bytes, rule: str, match: re.Match[bytes]) -> bool:
    key = (rule, match.start(), match.end(), hashlib.sha256(match.group(0)).hexdigest())
    blob_hash = REVIEWED_CIPHERTEXT_MATCHES.get(key)
    return blob_hash is not None and hashlib.sha256(data).hexdigest() == blob_hash


def scan_bytes(path: str, data: bytes) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()
    for rule, pattern in DIRECT_SECRET_RULES:
        for match in pattern.finditer(data):
            if is_allowed_placeholder(match.group(0)):
                continue
            if _reviewed_ciphertext_match(data, rule, match):
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


def path_findings(
    paths: Iterable[str], *, verified_residuals: frozenset[str] = frozenset()
) -> list[Finding]:
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
        if re.search(r"(^|/)annotation_key[^/]*\.csv(?:\.sha256)?$", lowered):
            findings.append(Finding(path_string, "private-annotation-key", "private linkage keys cannot be tracked"))
        if re.search(r"(^|/)(?:coder[^/]*|[^/]*_coder[^/]*)\.csv$", lowered):
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
        if suffix in RESTRICTED_MODEL_SUFFIXES and not (
            suffix == ".safetensors" and path_string in verified_residuals
        ):
            findings.append(
                Finding(path_string, "restricted-model-artifact", "model weights cannot be tracked")
            )
    return findings


def ignored_private_file_findings(repo: Path) -> list[Finding]:
    candidates = [repo / ".env", repo / "checkpoint.md", repo / "steering" / ".env"]
    candidates.extend(repo.glob("data/**/annotation_key*.csv*"))
    for folder in ("data", "tmp"):
        candidates.extend(repo.glob(f"{folder}/**/coder*.csv"))
        candidates.extend(repo.glob(f"{folder}/**/*_coder*.csv"))

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
        excludes = []
        for path, digest in PRESERVED_SOURCE_BYTES.items():
            if label == "index-whitespace":
                source = _git(repo, "show", ":" + path, check=False)
                data = source.stdout if source.returncode == 0 else None
            else:
                candidate = repo / path
                data = candidate.read_bytes() if candidate.is_file() and not candidate.is_symlink() else None
            if data is not None and hashlib.sha256(data).hexdigest() == digest:
                excludes.append(":(exclude)" + path)
        result = _git(repo, *args, "--", ".", *excludes, check=False)
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
        source_path = RELEASE_MANIFEST_ALIASES.get(manifest_path)
        if source_path is not None:
            source_manifest = manifests.get(source_path)
            if source_manifest is None:
                findings.append(Finding(
                    manifest_path, "missing-release-alias-source",
                    f"canonical release manifest {source_path} is absent from the Git index",
                ))
                continue
            if raw_manifest != source_manifest:
                findings.append(Finding(
                    manifest_path, "release-alias-mismatch",
                    f"indexed manifest bytes differ from {source_path}",
                ))
                continue
        try:
            manifest = json.loads(raw_manifest)
        except (UnicodeDecodeError, json.JSONDecodeError):
            findings.append(
                Finding(manifest_path, "invalid-release-manifest", "release manifest is not valid JSON")
            )
            continue
        files = manifest.get("files") if isinstance(manifest, dict) else None
        hash_only = manifest_path in HASH_MAP_MANIFESTS
        if hash_only:
            if (not isinstance(manifest, dict)
                    or manifest.get("schema") != HASH_MAP_MANIFESTS[manifest_path]
                    or not isinstance(files, dict) or not files
                    or type(manifest.get("file_count")) is not int
                    or manifest["file_count"] != len(files)
                    or manifest.get("release") != str(PurePosixPath(manifest_path).parent)):
                findings.append(Finding(manifest_path, "invalid-release-manifest",
                                        "known hash-map manifest has invalid schema or inventory"))
                continue
            files = [{"path": path, "sha256": digest, "bytes": None}
                     for path, digest in files.items()]
        if not isinstance(files, list):
            findings.append(
                Finding(manifest_path, "invalid-release-manifest", "release manifest has no files list")
            )
            continue
        base = PurePosixPath(source_path or manifest_path).parent
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
            if (not isinstance(item["path"], str)
                    or (not hash_only and (type(item["bytes"]) is not int or item["bytes"] < 0))
                    or not residual_audit.digest(item["sha256"])):
                findings.append(Finding(manifest_path, "invalid-release-entry",
                                        f"release file entry {index} has invalid path, bytes, or sha256"))
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
            size_matches = hash_only or actual_bytes == item["bytes"]
            if not size_matches:
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
            if size_matches and actual_sha == str(item["sha256"]):
                verified_entries += 1
    return findings, verified_entries


def audit_repository(repo: Path) -> dict[str, object]:
    repo = repo.resolve()
    modes: dict[str, str] = {}
    entries, findings = index_entries(repo, modes=modes)
    paths = [path for path, _sha in entries]
    blocked, size_findings = residual_size_preflight(repo, entries)
    findings.extend(size_findings)

    missing = sorted(REQUIRED_PUBLIC_FILES.difference(paths))
    findings.extend(
        Finding(path, "missing-public-provenance", "required public provenance file is absent")
        for path in missing
    )

    scanned_bytes = 0
    scanned_files = 0
    blob_records: dict[str, tuple[int, str]] = {}
    release_manifests: dict[str, bytes] = {}
    for path, data in iter_index_blobs(repo, (entry for entry in entries if entry[0] not in blocked)):
        scanned_files += 1
        scanned_bytes += len(data)
        blob_records[path] = (len(data), hashlib.sha256(data).hexdigest())
        if is_release_manifest(path):
            release_manifests[path] = data
        findings.extend(scan_blob(path, data))

    manifest_findings, verified_release_entries = release_manifest_findings(
        release_manifests, blob_records
    )
    findings.extend(manifest_findings)
    oids = dict(entries)

    def read_indexed(path: str, limit: int) -> bytes:
        record = blob_records.get(path)
        if record is None or record[0] > limit:
            raise residual_audit.ResidualAuditError("missing-or-oversized-indexed-evidence")
        return _git(repo, "cat-file", "blob", oids[path]).stdout

    verified_residuals: frozenset[str] = frozenset()
    try:
        verified_residuals = residual_audit.approved_residual_paths(paths, blob_records, modes, read_indexed)
    except residual_audit.ResidualAuditError as exc:
        findings.append(Finding(residual_audit.RELEASE_ROOT, "invalid-residual-release", str(exc)))
    except (KeyError, TypeError, ValueError, RecursionError):
        findings.append(Finding(residual_audit.RELEASE_ROOT, "invalid-residual-release",
                                "malformed residual release evidence"))
    try:
        verified_residuals |= exposure_audit.approved_residual_paths(paths, blob_records, modes, read_indexed)
    except exposure_audit.ExposureAuditError as exc:
        findings.append(Finding(exposure_audit.RELEASE_ROOT, "invalid-exposure-release", str(exc)))
    except (KeyError, TypeError, ValueError, RecursionError):
        findings.append(Finding(exposure_audit.RELEASE_ROOT, "invalid-exposure-release",
                                "malformed exposure release evidence"))
    findings.extend(path_findings(paths, verified_residuals=verified_residuals))
    findings.extend(ignored_private_file_findings(repo))
    findings.extend(whitespace_findings(repo))
    findings = sorted(findings, key=lambda row: (row.path, row.line or 0, row.rule))
    return {
        "status": "pass" if not findings else "fail",
        "scope": "git-index-plus-private-ignore-and-whitespace-checks",
        "tracked_files_scanned": scanned_files,
        "tracked_bytes_scanned": scanned_bytes,
        "residual_captures_verified": len(verified_residuals),
        "oversized_safetensors_rejected": len(blocked),
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
