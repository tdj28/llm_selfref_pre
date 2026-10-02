"""Durable, write-once local stop signal shared by judges and the controller."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import stat

SCHEMA = "bilingual-judging-halt-b1"
FILENAME = "JUDGING-HALT.json"


class JudgingHalt(ValueError):
    """A present or unverifiable stop signal forbids continued execution."""


def _bindings(plan_hash, freeze):
    if (not isinstance(plan_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", plan_hash)
            or not isinstance(freeze, str) or not re.fullmatch(r"[0-9a-f]{40}", freeze)):
        raise JudgingHalt("Full plan and freeze hashes required for judging halt")


def _path(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise JudgingHalt("Symlinked judging halt paths are forbidden")
    return path


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate halt key")
        result[key] = value
    return result


def _read(path, plan_hash, freeze):
    _bindings(plan_hash, freeze)
    path = _path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise JudgingHalt("Cannot read judging halt signal; execution forbidden") from exc
    try:
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
                raise ValueError("Invalid halt file")
            data = handle.read(4097)
        if len(data) > 4096:
            raise ValueError("Oversized halt file")
        value = json.loads(data, object_pairs_hook=_object)
        if (not isinstance(value, dict)
                or set(value) != {"schema", "plan_sha256", "freeze_commit", "error_type"}
                or value["schema"] != SCHEMA or value["plan_sha256"] != plan_hash
                or value["freeze_commit"] != freeze
                or not isinstance(value["error_type"], str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", value["error_type"])):
            raise ValueError("Halt schema or bindings differ")
    except (OSError, ValueError, TypeError) as exc:
        raise JudgingHalt("Malformed or mismatched judging halt signal; execution forbidden") from exc
    return value


def check_halt(path, plan_hash, freeze):
    """Return None only when absent; every existing signal fails closed."""
    value = _read(path, plan_hash, freeze)
    if value is not None:
        raise JudgingHalt("Judging halt is permanent for this run: " + value["error_type"])


def write_halt(path, plan_hash, freeze, error_type):
    """Persist the first error type only; never overwrite or clear a signal.

    Exclusive creation makes concurrent writers immutable. A process dying during
    its write leaves a malformed file, which the reader treats as a stop as well.
    File and directory fsync make a completed publication durable.
    """
    _bindings(plan_hash, freeze)
    if not isinstance(error_type, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", error_type):
        raise JudgingHalt("Invalid judging halt error type")
    path = _path(path)
    existing = _read(path, plan_hash, freeze)
    if existing is not None:
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    _path(path)
    value = {"schema": SCHEMA, "plan_sha256": plan_hash, "freeze_commit": freeze, "error_type": error_type}
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        existing = _read(path, plan_hash, freeze)
        if existing is None:
            raise JudgingHalt("Judging halt disappeared during publication") from None
        return existing
    with os.fdopen(fd, "wb") as handle:
        handle.write((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii"))
        handle.flush()
        os.fsync(handle.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return value


@contextmanager
def halt_on_error(judge_root, plan_hash, freeze, *, production):
    """Synthetic calls never publish, but cannot bypass an existing stop signal."""
    path = Path(judge_root).parent / FILENAME
    check_halt(path, plan_hash, freeze)
    try:
        yield
    except BaseException as exc:
        if production:
            write_halt(path, plan_hash, freeze, type(exc).__name__)
        raise
