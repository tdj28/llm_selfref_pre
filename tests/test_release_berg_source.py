import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import release_berg_source as r
from experiments.sae_assay_diagnostic.budget import EventLedger


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    repo = tmp_path/"repo"
    repo.mkdir()
    monkeypatch.setattr(r.protocol, "ROOT", repo)
    freeze = "a"*40
    source, inputs = b"synthetic frozen source\n", b"synthetic input\n"
    plan = {"schema": "berg_source_public_v1", "rows": [{"id": "one", "capture": False}],
            "model": {"id": "synthetic-model", "revision": "c"*40, "precision": "bf16"},
            "sae": {"id": "synthetic-sae", "revision": "d"*40, "sha256": "e"*64},
            "source_hashes": {"src/science.py": hashlib.sha256(source).hexdigest()},
            "input_hashes": {"data/input.csv": hashlib.sha256(inputs).hexdigest()}}
    path = repo/"PLAN.json"
    path.write_text(r.protocol.canonical(plan)+"\n")
    blobs = {"PLAN.json": path.read_bytes(), "src/science.py": source, "data/input.csv": inputs}
    calls = []

    def git(*args):
        calls.append(args)
        if args == ("cat-file", "-t", freeze):
            return b"commit\n"
        if len(args) == 5 and args[:4] == ("ls-tree", "-z", freeze, "--"):
            name = args[4]
            if name not in blobs:
                return b""
            oid = hashlib.sha1(blobs[name]).hexdigest()
            return f"100644 blob {oid}\t{name}\0".encode()
        if args[:2] == ("cat-file", "blob"):
            return next(raw for raw in blobs.values() if hashlib.sha1(raw).hexdigest() == args[2])
        raise ValueError("Cannot verify local frozen Git object")

    monkeypatch.setattr(r, "_git", git)
    for name in set(r.reporting_sources()) | set(r.reporting_sources(True)):
        p = repo/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("synthetic reporting source\n")
    out = tmp_path/"release"
    (out/"rows").mkdir(parents=True)
    ids = ["qualification-live", "one"]
    plan_hash = r.protocol.sha(path)
    ledger = EventLedger(out/"receipts.jsonl", plan_hash, freeze, ids)
    for rid in ids:
        row_path = out/"rows"/(rid+".json")
        row_path.write_text(json.dumps({"id": rid})+"\n")
        ledger.bind("dispatch:"+rid, {"kind": "dispatch", "row_id": rid})
        ledger.append_row(rid, {"path": "rows/"+rid+".json", "sha256": r.protocol.sha(row_path)})
    (out/"DONE-all.json").write_text(r.protocol.canonical({"pass": True, "rows": 2,
        "plan_sha256": plan_hash, "freeze_commit": freeze})+"\n")
    (out/"analysis").mkdir()
    (out/"analysis/summary.json").write_text('{"primary":{}}\n')
    (out/"model-bf16-load-00002.json").write_text(json.dumps({
        "model_id": plan["model"]["id"], "model_revision": plan["model"]["revision"],
        "precision": "bf16", "sae_id": plan["sae"]["id"], "sae_revision": plan["sae"]["revision"],
        "sae_sha256": plan["sae"]["sha256"]})+"\n")
    raw_files = r._files(out)
    receipt = {"freeze_commit": freeze, "plan_sha256": plan_hash,
               "artifacts": {name: r.protocol.sha(p) for name, p in raw_files.items()}}
    (out/"retrieval_and_cost.json").write_text(json.dumps(receipt)+"\n")
    audit = {"pass": True, "partial": False, "generations": 1, "expected": 1,
             "plan_sha256": plan_hash, "freeze_commit": freeze, "receipts_verified": True}
    (out/"PUBLICATION_AUDIT.json").write_text(json.dumps(audit)+"\n")
    return SimpleNamespace(repo=repo, out=out, path=path, plan=plan, freeze=freeze,
                           blobs=blobs, calls=calls, audit=audit, raw_files=raw_files, receipt=receipt)


@pytest.fixture
def closed(tmp_path):
    base = tmp_path/"controller"
    root = base/"retrievals"/"one"
    root.mkdir(parents=True)
    (root/"safe.json").write_text('{"test_only":true}\n')
    ledger = EventLedger(base/"events.jsonl", "a"*64, "b"*40, [])
    ledger.bind("created", {"id": "synthetic-pod", "name": "codex-berg-source-20260930-main-test"})
    receipt = ledger.bind("retrieval:one", {"pod_id": "synthetic-pod", "directory": str(root),
                                           "artifacts": {"safe.json": r.protocol.sha(root/"safe.json")}})
    (base/"final-retrieval.json").write_text(json.dumps(receipt))
    ledger.bind("delete-response", {"pod_id": "synthetic-pod", "status": 204})
    ledger.bind("closed", {"pod_id": "synthetic-pod", "get_status": 404, "within_limits": True})
    return base, root


def test_verified_closed_retrieval(closed):
    base, root = closed
    returned, files, closure, _ = r.lifecycle(base, "a"*64, "b"*40)
    assert returned == root and set(files) == {"safe.json"}
    assert closure["get_status"] == 404


def test_tampered_retrieval_is_rejected(closed):
    base, root = closed
    (root/"safe.json").write_text('{}\n')
    with pytest.raises(ValueError, match="Changed retrieved artifact"):
        r.lifecycle(base, "a"*64, "b"*40)


def test_unreceipted_file_is_rejected(closed):
    base, root = closed
    (root/"extra.txt").write_text('extra')
    with pytest.raises(ValueError, match="inventory"):
        r.lifecycle(base, "a"*64, "b"*40)


def test_allowlist_excludes_keys_caches_and_private_ledger():
    names = r.allowed({"rows": [{"id": "one", "capture": True}, {"id": "two", "capture": False}]})
    assert {"rows/one.json", "rows/two.json", "rows/capture-one.json"} <= names
    assert not {".env", "events.jsonl", "model.safetensors", "id_ed25519"} & names
    with pytest.raises(ValueError, match="Unsafe"):
        r.allowed({"rows": [{"id": "../../private", "capture": True}]})


def test_complete_frozen_inventory_allows_signed_dose_filenames():
    plan = {"rows": r.protocol.inventory()}
    names = r.allowed(plan)
    assert all("rows/"+row["id"]+".json" in names for row in plan["rows"])
    assert any("+0.7" in name for name in names)


def test_ensemble_allowlist_is_specific_and_namespace_not_interchangeable(closed):
    names = r.allowed({"schema":"berg_random_subset_public_v1", "rows":[{"id":"target-1-+1","capture":False}]})
    assert "analysis/rates.csv" in names and "analysis/curves.csv" not in names
    assert "static-directions.json" not in names
    base,_ = closed
    with pytest.raises(ValueError,match="namespace"):
        r.lifecycle(base,"a"*64,"b"*40,ensemble=True)


def test_missing_ledger_does_not_create_one(tmp_path):
    with pytest.raises(ValueError, match="Missing regular ledger"):
        r.lifecycle(tmp_path, "a"*64, "b"*40)
    assert not (tmp_path/"events.jsonl").exists()


def test_destination_never_overwritten(tmp_path):
    with pytest.raises(ValueError, match="overwrite"):
        r.build(tmp_path, tmp_path/"plan", "b"*40, tmp_path)


def test_snapshot_lineage_preserves_earlier_raw_hashes(closed):
    base, _ = closed
    ledger = EventLedger(base/"events.jsonl", "a"*64, "b"*40, [])
    ledger.bind("retrieval:synthetic-raw", {"utc": "2026-10-01T00:00:00+00:00",
        "artifacts": {"rows/one.json": "c"*64, "controller.log": "d"*64,
                      "rows/two.pending": "f"*64}})
    result = r.snapshot_lineage(base, {"rows/one.json": "c"*64}, "a"*64, "b"*40)
    assert result["snapshots"][-1]["raw_rows"] == 1
    assert "controller.log" not in result["snapshots"][-1]["artifacts"]
    assert result["snapshots"][-1]["unpublished_inflight_files"] == {"rows/two.pending": "f"*64}
    with pytest.raises(ValueError, match="changed or disappeared"):
        r.snapshot_lineage(base, {"rows/one.json": "e"*64}, "a"*64, "b"*40)


def test_manifest_requires_original_retrieved_bytes(candidate):
    c = candidate
    raw = c.out/"rows/one.json"
    original = raw.read_bytes()
    raw.write_text('{}\n')
    with pytest.raises(ValueError, match="Original retrieved bytes changed"):
        r.manifest(c.out, c.path, c.freeze)
    raw.write_bytes(original)
    assert r.manifest(c.out, c.path, c.freeze)["files"] == len(c.raw_files)+2
    with pytest.raises(ValueError, match="already sealed"):
        r.manifest(c.out, c.path, c.freeze)


def test_freeze_uses_commit_blobs_not_head_or_working_tree(candidate):
    c = candidate
    assert r.verify_freeze(c.path, c.freeze) == c.plan
    # Current HEAD and current source bytes are irrelevant to the historical binding.
    (c.repo/"src").mkdir()
    (c.repo/"src/science.py").write_text("later working-tree contents\n")
    assert r.verify_freeze(c.path, c.freeze) == c.plan
    assert all("HEAD" not in args for args in c.calls)


@pytest.mark.parametrize("name", ["PLAN.json", "src/science.py", "data/input.csv"])
def test_freeze_rejects_changed_git_blobs(candidate, name):
    c = candidate
    c.blobs[name] = b"wrong frozen bytes\n"
    with pytest.raises(ValueError, match="frozen Git blob|Frozen Git blob"):
        r.verify_freeze(c.path, c.freeze)


def test_freeze_rejects_working_plan_drift_unknown_commit_and_unsafe_paths(candidate):
    c = candidate
    for freeze in ("main", "a"*12, "b"*40):
        with pytest.raises(ValueError):
            r.verify_freeze(c.path, freeze)
    for name in ("../outside", "/outside"):
        with pytest.raises(ValueError, match="artifact path"):
            r._frozen_blob(c.freeze, name)
    c.path.write_text(c.path.read_text()+" ")
    with pytest.raises(ValueError, match="Plan differs"):
        r.verify_freeze(c.path, c.freeze)


def test_git_verification_is_offline_read_only(monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"commit\n")
    monkeypatch.setattr(r.subprocess, "run", run)
    assert r._git("cat-file", "-t", "a"*40) == b"commit\n"
    command, kwargs = calls[0]
    assert command == ["git", "--no-replace-objects", "-C", str(r.protocol.ROOT), "cat-file", "-t", "a"*40]
    assert kwargs["env"]["GIT_NO_LAZY_FETCH"] == "1"


@pytest.mark.parametrize("change", ["missing", "failed", "partial", "freeze", "plan", "count", "receipts"])
def test_seal_requires_passed_bound_publication_audit(candidate, change):
    c = candidate
    path = c.out/"PUBLICATION_AUDIT.json"
    if change == "missing":
        path.unlink()
    else:
        key, value = {"failed": ("pass", False), "partial": ("partial", True),
                      "freeze": ("freeze_commit", "b"*40), "plan": ("plan_sha256", "b"*64),
                      "count": ("generations", 0), "receipts": ("receipts_verified", False)}[change]
        c.audit[key] = value
        path.write_text(json.dumps(c.audit))
    with pytest.raises((ValueError, FileNotFoundError)):
        r.manifest(c.out, c.path, c.freeze)
    assert not (c.out/"RELEASE_MANIFEST.json").exists()


@pytest.mark.parametrize("name,content", [
    ("notes.md", b"/Users/synthetic/private-context"),
    ("metadata.json", b'{"path":"\\u002fUsers\\u002fsynthetic"}'),
    ("coder_results.csv", b"item,rating\n1,0\n"),
    ("figure.pdf", b"%PDF-1.4\n/Users/synthetic/private-context"),
    ("figure.png", b"\x89PNG\r\n\x1a\n/Users/synthetic/private-context"),
])
def test_seal_scans_added_files(candidate, name, content):
    c = candidate
    (c.out/name).write_bytes(content)
    with pytest.raises(ValueError, match="Private|private"):
        r.manifest(c.out, c.path, c.freeze)
    assert not (c.out/"RELEASE_MANIFEST.json").exists()


def test_seal_scans_every_file_and_binds_reporting_dependencies(candidate, monkeypatch):
    c = candidate
    (c.out/"figure.png").write_bytes(b"\x89PNG\r\n\x1a\nsynthetic")
    (c.out/"figure.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    scanned = []
    scan = r._scan_public_file
    def record(name, path, plan=None):
        scanned.append(name)
        scan(name, path, plan=plan)
    monkeypatch.setattr(r, "_scan_public_file", record)
    r.manifest(c.out, c.path, c.freeze)
    manifest = json.loads((c.out/"RELEASE_MANIFEST.json").read_text())
    assert set(scanned) == {row["path"] for row in manifest["files"]}
    assert {"experiments/berg_source_figures.py", "experiments/berg_source_diagnostics.py"} <= set(manifest["reporting_source_hashes"])
    assert {"experiments/berg_source_diagnostics.py", "experiments/berg_ensemble_diagnostics.py"} <= set(r.reporting_sources(True))
    r.verify_reporting_sources(manifest)


@pytest.mark.parametrize("order", ["returns_first", "all_dispatches_first", "missing", "wrong_id"])
def test_receipt_chronology_rejects_hash_valid_invalid_traces(candidate, tmp_path, order):
    c = candidate
    root = tmp_path/"chronology"
    (root/"rows").mkdir(parents=True)
    ids = ["qualification-live", "one"]
    ledger = EventLedger(root/"receipts.jsonl", r.protocol.sha(c.path), c.freeze, ids)
    for rid in ids:
        (root/"rows"/(rid+".json")).write_text("{}\n")
    def dispatch(rid):
        name = "wrong:"+rid if order == "wrong_id" else "dispatch:"+rid
        ledger.bind(name, {"kind": "dispatch", "row_id": rid})
    def returned(rid):
        ledger.append_row(rid, {"path": "rows/"+rid+".json", "sha256": r.protocol.sha(root/"rows"/(rid+".json"))})
    if order == "returns_first":
        for rid in ids: returned(rid)
        for rid in ids: dispatch(rid)
    elif order == "all_dispatches_first":
        for rid in ids: dispatch(rid)
        for rid in ids: returned(rid)
    else:
        for rid in ids:
            dispatch(rid)
            if order != "missing": returned(rid)
    with pytest.raises(ValueError, match="chronology|event ID"):
        r.verify_receipts(root, c.plan, c.freeze)


def test_serial_receipts_allow_non_dispatch_metadata(candidate):
    c = candidate
    ledger = EventLedger(c.out/"receipts.jsonl", r.protocol.sha(c.path), c.freeze, ["qualification-live", "one"])
    ledger.bind("technical-note", {"kind": "metadata", "test_only": True})
    r.verify_receipts(c.out, c.plan, c.freeze)


def test_synthetic_build_audit_is_bound_and_sealable(candidate, monkeypatch, tmp_path):
    c = candidate
    monkeypatch.setattr(r.protocol, "load_plan", lambda path: c.plan)
    monkeypatch.setattr(r, "lifecycle", lambda *args, **kwargs: (
        c.out, c.raw_files, {"get_status": 404, "within_limits": True},
        {"artifacts": c.receipt["artifacts"]}))
    monkeypatch.setattr(r, "snapshot_lineage", lambda *args: {"snapshots": []})
    monkeypatch.setattr(r.analysis, "audit", lambda *args, **kwargs: {
        "pass": True, "partial": False, "expected": 1, "generations": 1})
    monkeypatch.setattr(r, "validate_capture_schedule", lambda *args: {"complete": True})
    destination = tmp_path/"built"
    report = r.build(tmp_path/"unused-controller", c.path, c.freeze, destination)
    assert report["freeze_commit"] == c.freeze and report["plan_sha256"] == r.protocol.sha(c.path)
    assert report["receipts_verified"] is True
    r.verify_publication(destination, c.plan, r.protocol.sha(c.path), c.freeze)
    assert r.manifest(destination, c.path, c.freeze)["files"] == len(c.raw_files)+3


@pytest.mark.parametrize("mode,kind", [("120000", "blob"), ("040000", "tree")])
def test_frozen_paths_must_be_regular_blobs(candidate, monkeypatch, mode, kind):
    c = candidate
    original = r._git
    def git(*args):
        if args[:2] == ("ls-tree", "-z"):
            return f"{mode} {kind} {'b'*40}\tPLAN.json\0".encode()
        return original(*args)
    monkeypatch.setattr(r, "_git", git)
    with pytest.raises(ValueError, match="regular Git blob"):
        r.verify_freeze(c.path, c.freeze)


@pytest.fixture
def paired_plan():
    rows = []
    for family in [f"feature-{f}" for f in r.protocol.TARGET_IDS] + [
            "aggregate-target", "aggregate-control-1", "aggregate-control-2", "aggregate-control-3"]:
        dose = .7 if family.startswith("feature-") else .5
        for seed in (101, 202):
            for coefficient in (-dose, dose):
                rows.append({"id": f"{family}-{seed}-{coefficient:+.1f}-notebook-0.6-128",
                             "family": family, "seed": seed, "coefficient": coefficient,
                             "capture": True, "prompt": "notebook", "temperature": .6, "cap": 128})
    return {"schema": "berg_source_public_v1", "rows": rows}


def paired_records(plan, output_length=1, numeric="0.125"):
    for spec in plan["rows"]:
        for history in ("zero", "steered"):
            for turn in (1, 2):
                for relative in range(1+min(4, output_length)):
                    for layer in (50, 65, 78):
                        for transport in ["identity", "jacobian"]+[f"random_j_{i}" for i in range(1, 6)]:
                            for group in ("deception", "roleplay", "honesty", "hedging", "experience", "intervention", "unrelated"):
                                yield dict(zip(r.PAIRED_CSV_HEADER, (
                                    spec["id"], spec["family"], spec["seed"], spec["coefficient"],
                                    history, turn, layer, 100+relative, relative,
                                    "generated" if relative else "last_prompt", transport, group,
                                    (f"feature-30032-{spec['seed']}-+0.0-notebook-0.6-128"
                                     if history == "zero" else spec["id"]),
                                    output_length, relative > 0 and relative == output_length,
                                    numeric, numeric, numeric if layer == 50 else "",
                                    numeric if layer == 50 else "", numeric, numeric, numeric, numeric)))


def write_paired(path, rows, header=r.PAIRED_CSV_HEADER):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def test_large_paired_csv_streams_valid_grid_above_generic_cap(tmp_path, paired_plan, monkeypatch):
    path = tmp_path/"paired_positions.csv"
    write_paired(path, paired_records(paired_plan, output_length=8, numeric="0."+"1"*30))
    assert r.MAX_TEXT_BYTES == 32*1024**2
    assert r.MAX_TEXT_BYTES < path.stat().st_size < r.PAIRED_CSV_MAX_BYTES == 64*1024**2
    def no_whole_file_read(self, *args, **kwargs):
        raise AssertionError("Scanner must stream, not materialize the CSV")
    monkeypatch.setattr(Path, "read_bytes", no_whole_file_read)
    monkeypatch.setattr(Path, "read_text", no_whole_file_read)
    r._scan_public_file(r.PAIRED_CSV, path, plan=paired_plan)


def test_paired_csv_accepts_terminal_and_later_layer_nulls(tmp_path, paired_plan):
    path = tmp_path/"paired.csv"
    rows = paired_records(paired_plan, output_length=1)
    def nullable():
        for row in rows:
            row["all_lexicon_static_cosine"] = ""
            yield row
    write_paired(path, nullable())
    r._scan_public_file(r.PAIRED_CSV, path, plan=paired_plan)


@pytest.mark.parametrize("name", ["secondary/unrelated.csv", "paired_positions.csv",
                                  "other/paired_positions.csv", "secondary/PAIRED_POSITIONS.csv"])
def test_oversized_unrelated_csv_never_gets_exception(tmp_path, paired_plan, name):
    path = tmp_path/"unrelated.csv"
    with path.open("wb") as handle:
        handle.write(b"/Users/synthetic/private-file\n")
        handle.truncate(32*1024**2+1)
    with pytest.raises(ValueError, match="size bound"):
        r._scan_public_file(name, path, plan=paired_plan)
    assert r.MAX_TEXT_BYTES == 32*1024**2


def test_paired_csv_64mib_cap_is_hard(tmp_path, paired_plan):
    path = tmp_path/"paired.csv"
    with path.open("wb") as handle:
        handle.truncate(64*1024**2+1)
    with pytest.raises(ValueError, match="64 MiB"):
        r._scan_public_file(r.PAIRED_CSV, path, plan=paired_plan)


@pytest.mark.parametrize("key,value", [
    ("source_id", "unknown"), ("family", "feature-999"), ("seed", "303"),
    ("coefficient", "0.5"), ("history", "other"), ("turn", "3"), ("layer", "51"),
    ("position", "131072"), ("position", "1.5"), ("relative_position", "5"),
    ("phase", "generated"), ("transport", "random_j_6"), ("group", "unknown"),
    ("originating_row_id", "unknown"), ("source_output_tokens", "129"),
    ("terminal_observation_only", "true"), ("normalized_logit_delta", "NaN"),
    ("linear_logit_delta", "inf"), ("static_linear_prediction", ""),
    ("all_lexicon_static_cosine", "1.1"), ("residual_delta_norm", "-1"),
    ("clean_residual_norm", "1e999"), ("clean_transport_norm", ""),
    ("edited_transport_norm", "1_000"),
])
def test_paired_csv_invalid_fields_fail(tmp_path, paired_plan, key, value):
    row = next(paired_records(paired_plan))
    row[key] = value
    path = tmp_path/"paired.csv"
    write_paired(path, [row])
    with pytest.raises(ValueError, match="paired CSV|Paired CSV"):
        r._scan_public_file(r.PAIRED_CSV, path, plan=paired_plan)


@pytest.mark.parametrize("mutation", ["header", "extra_field", "duplicate", "truncated", "metadata",
                                      "later_static", "overlong", "multiline"])
def test_paired_csv_schema_and_grid_fail_closed(tmp_path, paired_plan, mutation):
    first = next(paired_records(paired_plan))
    path = tmp_path/"paired.csv"
    rows = [first]
    header = r.PAIRED_CSV_HEADER
    if mutation == "header":
        header = tuple(reversed(header))
    elif mutation == "extra_field":
        first["unexpected"] = "extra"
        header += ("unexpected",)
    elif mutation == "duplicate":
        rows.append(dict(first))
    elif mutation == "metadata":
        rows.append(dict(first, group="roleplay", position=101))
    elif mutation == "later_static":
        first["layer"] = 65
    elif mutation == "overlong":
        first["linear_logit_delta"] = "1"*2049
    elif mutation == "multiline":
        first["linear_logit_delta"] = "1\n2"
    write_paired(path, rows, header)
    with pytest.raises(ValueError, match="paired CSV|Paired CSV"):
        r._scan_public_file(r.PAIRED_CSV, path, plan=paired_plan)


def test_paired_csv_streaming_scans_private_paths_and_secret_patterns(tmp_path, paired_plan):
    path = tmp_path/"paired.csv"
    for content in ("/Users/synthetic/private-file", "sk-"+"Q"*24):
        row = next(paired_records(paired_plan))
        row["normalized_logit_delta"] = content
        write_paired(path, [row])
        with pytest.raises(ValueError, match="content scan|Private paired"):
            r._scan_public_file(r.PAIRED_CSV, path, plan=paired_plan)


def test_paired_csv_requires_known_source_plan_and_bounded_rows(tmp_path, paired_plan, monkeypatch):
    path = tmp_path/"paired.csv"
    records = paired_records(paired_plan)
    write_paired(path, [next(records), next(records)])
    for plan in (None, {"schema": "berg_random_subset_public_v1"},
                 {"schema": "berg_source_public_v1", "rows": paired_plan["rows"][:-1]}):
        with pytest.raises(ValueError, match="plan|inventory"):
            r._scan_public_file(r.PAIRED_CSV, path, plan=plan)
    assert r.PAIRED_CSV_MAX_ROWS == 117600
    monkeypatch.setattr(r, "PAIRED_CSV_MAX_ROWS", 1)
    with pytest.raises(ValueError, match="row bound"):
        r._scan_public_file(r.PAIRED_CSV, path, plan=paired_plan)
