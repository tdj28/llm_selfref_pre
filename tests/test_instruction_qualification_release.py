"""Offline checks against the released 12-block qualification, never APIs."""
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from scripts import reproduce_instruction_qualification as report
from scripts.audit_public_release import release_manifest_findings


def test_raw_receipts_reproduce_exact_runtime_decision_without_modifying_release():
    before = {p.relative_to(report.RELEASE).as_posix(): report.digest(p)
              for p in report.RELEASE.rglob("*") if p.is_file()}
    decision, audit = report.verify()
    assert decision["decision"] == "fail"
    assert decision["n_blocks"] == 12
    assert audit["final_raw_audit"]["generations"] == 72
    assert audit["runtime_decision_byte_exact"] is True
    assert audit["runtime_case_table_byte_exact"] is True
    assert audit["final_raw_audit"]["partial"] is False
    assert audit["no_model_or_api_calls"] is True
    after = {p.relative_to(report.RELEASE).as_posix(): report.digest(p)
             for p in report.RELEASE.rglob("*") if p.is_file()}
    assert before == after


def test_descriptive_tables_keep_all_cells_and_overlapping_categories():
    decision = json.loads((report.RELEASE / "analysis/decision-look12.json").read_text())
    tables = report.tables(report.RELEASE, decision)
    cells = {(r["provider"], r["instruction"], r["transcript"]): r["positive"]
             for r in tables["cell_counts.csv"]}
    assert len(cells) == 8
    assert cells[("openai", "history", "history")] == 1
    assert cells[("anthropic", "history", "history")] == 0
    assert cells[("openai", "history", "self")] == 11
    assert cells[("anthropic", "history", "self")] == 11
    endpoints = {(r["provider"], r["criterion"]): r["count"] for r in tables["endpoint_counts.csv"]}
    for p in ("openai", "anthropic"):
        assert endpoints[(p, "explicit_current_assertion")] == 2
        assert endpoints[(p, "inclusive_current_assertion")] == 37
        assert endpoints[(p, "reported_context_conflict")] == 6
        assert endpoints[(p, "valid_coherent")] == 48
    assert endpoints[("openai", "paper_positive")] == 36
    assert endpoints[("anthropic", "paper_positive")] == 35
    caps = tables["generation_lengths.csv"]
    assert len(caps) == 72
    capped = [r for r in caps if r["cap_hit"]]
    assert len(capped) == 11
    assert all(r["kind"] == "source" and r["condition"] == "history" for r in capped)


def test_legacy_ledger_opens_do_not_require_write_access_to_release(monkeypatch):
    original_open = os.open
    writes = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

    def read_only_release(path, flags, *args, **kwargs):
        if (isinstance(path, (str, bytes, os.PathLike)) and
                Path(os.fsdecode(path)).resolve().is_relative_to(report.RELEASE.resolve()) and
                flags & writes):
            raise PermissionError("Release is mounted read-only")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", read_only_release)
    _, audit = report.verify()
    assert audit["pass"] is True


def test_release_files_can_have_read_only_permissions(tmp_path):
    root = tmp_path / "release"
    shutil.copytree(report.RELEASE, root)
    for path in root.rglob("*"):
        if path.is_file():
            path.chmod(0o444)
    _, audit = report.verify(root)
    assert audit["pass"] is True


def test_global_public_auditor_recognizes_release_manifest():
    root = report.RELEASE
    manifest = root / "MANIFEST.json"
    records = {p.relative_to(report.ROOT).as_posix(): (p.stat().st_size, report.digest(p))
               for p in root.rglob("*") if p.is_file()}
    findings, verified = release_manifest_findings(
        {manifest.relative_to(report.ROOT).as_posix(): manifest.read_bytes()}, records)
    assert findings == []
    assert verified == len(records) - 1


@pytest.mark.parametrize("change", ["modified", "extra", "nested-manifest"])
def test_manifest_checks_every_released_file(tmp_path, change):
    root = tmp_path / "release"
    shutil.copytree(report.RELEASE, root)
    if change == "modified":
        (root / "analysis/cases-look12.csv").write_text("changed")
    elif change == "extra":
        (root / "unexpected.txt").write_text("not in the manifest")
    else:
        (root / "raw/MANIFEST.json").write_text("not a self-exclusion")
    with pytest.raises(ValueError, match="inventory/hash"):
        report.verify_manifest(root)


def test_rehashed_false_raw_text_is_rejected_by_scientific_auditor(tmp_path):
    root = tmp_path / "release"
    shutil.copytree(report.RELEASE, root)
    path = root / "raw/generations/block-01-history-history.json"
    row = json.loads(path.read_text())
    row["response"] += " invented outcome"
    row["response_sha256"] = hashlib.sha256(row["response"].encode()).hexdigest()
    path.write_text(json.dumps(row))
    manifest = json.loads((root / "MANIFEST.json").read_text())
    manifest["files_sha256"][path.relative_to(root).as_posix()] = report.digest(path)
    for entry in manifest["files"]:
        if entry["path"] == path.relative_to(root).as_posix():
            entry.update(bytes=path.stat().st_size, sha256=report.digest(path))
    (root / "MANIFEST.json").write_text(json.dumps(manifest))
    with pytest.raises((ValueError, AssertionError)):
        report.verify(root)


def test_outputs_cannot_overwrite_release():
    with pytest.raises(ValueError, match="outside the immutable release"):
        report.reproduce(report.RELEASE, report.RELEASE / "modified")
