"""Inspect indexed files without printing possible secret values."""

import pathlib
import re
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
SECRET = re.compile(
    rb"(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}"
    rb"|hf_[A-Za-z0-9]{30,}"
    rb"|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)"
)


def audit_entry(name, content):
    path = pathlib.PurePosixPath(name)
    errors = []
    private_names = {"checkpoint.md", "id_rsa", "id_ed25519"}
    if path.name.startswith(".env") or path.name in private_names:
        errors.append(f"private filename: {name}")
    if any(part in {".ssh", ".venv", "node_modules"} for part in path.parts):
        errors.append(f"private/cache directory: {name}")
    if SECRET.search(content):
        errors.append(f"possible credential: {name}")
    return errors


def main():
    files = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT
    ).decode().split("\0")
    errors = []
    for name in filter(None, files):
        content = subprocess.check_output(["git", "show", f":{name}"], cwd=ROOT)
        errors.extend(audit_entry(name, content))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Public-file audit passed: {len(list(filter(None, files)))} indexed files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
