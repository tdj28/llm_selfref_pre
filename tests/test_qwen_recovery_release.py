"""Offline synthetic receipt tests; never dispatches to a model service."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import json
from pathlib import Path
import shutil

import pytest

from experiments import qwen_judge_recovery as q, qwen_recovery_release as r
from experiments.openrouter_swap.ledger import Halted, Ledger
from experiments.openrouter_swap.providers import TransportError
from tests.test_qwen_judge_recovery import sender

FREEZE = "a366b664855dfed12590803134a7841844360175"


@pytest.fixture(scope="module")
def data():
    return q.source()


def make_run(path, data, *, fail_first_two=False, pending=False):
    binding = {"freeze": FREEZE, "plan_sha256": q.common.sha(q.ROOT / q.PLAN),
               "original_manifest_sha256": q.MANIFEST_SHA, "original_release_commit": q.RELEASE_COMMIT}
    stamp = datetime.now(timezone.utc).isoformat()
    funded = {"confirmed": True, "as_of_utc": stamp, "account_balance_usd": "200",
              "scope_prior_bound_usd": str(q.PRIOR), "scope_other_commitments_usd": "45",
              "kolibri_holdback_usd": "45", "repeated_remaining_holdback_usd": "100",
              "other_account_holdback_usd": "0", "evidence_sha256": "c" * 64}
    launch = path / "launches" / ("d" * 32)
    r._write(path / "runtime.json", binding)
    with Ledger(path / "raw", cap="2", screen_cap="2") as ledger:
        r._write(launch / "start.json", {**binding, "preflight": funded,
                 "utc": datetime.now(timezone.utc).isoformat(), "calls_before": 0,
                 "journal_before_sha256": q.common.sha(path / "raw/events.jsonl")})
        normal = sender(data)
        attempts = []
        def send(request):
            attempts.append(request)
            if fail_first_two and len(attempts) <= 2:
                raise TransportError(503)
            return normal(request)
        if pending:
            request = data["targets"][q.TARGETS[0]]["original"]["request"]
            ledger.reserve(q.attempt_id(q.TARGETS[0], 1), request, q.reservation(data["spec"], request),
                           "main", q.attempt_metadata(q.TARGETS[0], 1, FREEZE, binding["plan_sha256"]))
            report = None
        else:
            report = q.recover(ledger, data, FREEZE, binding["plan_sha256"], send, funded, sleep=lambda s: None)
            rows = q.project(data, report)
            r._write(launch / "recovery_report.json", report)
            r._write(launch / "recovery_main_rows.json", rows)
            r._write(launch / "recovery_main_analysis.json", r.analysis.analyze(rows, "main"))
        r._write(launch / "finish.json", {**binding, "all_three_labels_recovered": bool(report and not report["remaining_missing"]),
                 "new_cost_bound_usd": str(ledger.spent()), "calls_after": len(ledger.rows()),
                 "journal_after_sha256": q.common.sha(path / "raw/events.jsonl")})
    return report


@pytest.fixture(scope="module")
def bundle(tmp_path_factory, data):
    root = tmp_path_factory.mktemp("qwen-recovery-release").resolve()
    run, release = root / "run", root / "release"
    make_run(run, data)
    original = q.common.sha(q.ROOT / q.ORIGINAL / "MANIFEST.json")
    result = r.build(run, release)
    assert q.common.sha(q.ROOT / q.ORIGINAL / "MANIFEST.json") == original == q.MANIFEST_SHA
    return run, release, result


def remanifest(root):
    (root / "MANIFEST.json").unlink()
    r._write(root / "MANIFEST.json", {"schema": "qwen-recovery-manifest-v1",
                                      "files": q.release._entries(r._inventory(root))})


def test_roundtrip_preserves_raw_and_only_three_slots(bundle, data):
    run, root, result = bundle
    assert result["pass"] and result["render_verified"] and result["status"] == "recovered"
    assert gzip.decompress((root / "raw/events.jsonl.gz").read_bytes()) == (run / "raw/events.jsonl").read_bytes()
    rows = r._json(root / "recovery_main_rows.json")
    assert {row["id"] for row, old in zip(rows, data["rows"]) if row != old} == {c.split(":")[1] for c in q.TARGETS}
    release = r._json(root / "RELEASE.json")
    assert release["original_release_status"] == "incomplete" and release["new_response_generations"] == 0
    assert release["original_unknown_charges_retained_usd"] == "0.96522800"
    assert release["response_model"] == r.MODEL and release["primary_family"]["fixed_family_size"] == 4
    assert release["primary_family"]["planned_models"] == ["qwen", "mistral"]
    assert r.verify(root, result["manifest_sha256"])["pass"]


def test_exporter_is_outside_scientific_closure():
    assert not set(r.SOURCES) & set(r._json(q.ROOT / q.PLAN)["source_hashes"])
    assert not set(r.SOURCES) & set(q.SOURCES)


def test_original_completed_labels_and_unrun_model_unchanged(bundle, data):
    after = r._json(bundle[1] / "recovery_main_rows.json")
    for old, new in zip(data["rows"], after):
        assert new.get("response") == old.get("response")
        if old["model"] == "mistral":
            assert new == old
        else:
            assert new["labels"]["opus"] == old["labels"]["opus"]
            assert new["labels"]["astra"]["paper"] == old["labels"]["astra"]["paper"]


@pytest.mark.parametrize("name", ["recovery_main_rows.json", "recovery_main_analysis.json",
                                "logical_projection.json", "RELEASE.json", "figures/figure_data.json",
                                "evidence/values.json", "PROVENANCE.json"])
def test_rehashed_derived_tampering_rejected(bundle, tmp_path, name):
    root = tmp_path / "copy"
    shutil.copytree(bundle[1], root)
    value = r._json(root / name)
    if isinstance(value, list):
        value[0]["fabricated"] = True
    else:
        value["fabricated"] = True
    (root / name).unlink()
    r._write(root / name, value)
    remanifest(root)
    with pytest.raises(Halted):
        r.verify(root)


def test_manifest_anchor_and_render_reject_tampering(bundle, tmp_path):
    root = tmp_path / "copy"
    shutil.copytree(bundle[1], root)
    image = root / "figures/primary_contrasts.png"
    image.write_bytes(image.read_bytes() + b"altered")
    with pytest.raises(Halted, match="hashes"):
        r.verify(root)
    remanifest(root)
    with pytest.raises(Halted, match="manifest"):
        r.verify(root, bundle[2]["manifest_sha256"])
    with pytest.raises(Halted, match="Figure"):
        r.verify(root, verify_render=True)


def test_private_files_not_copied_and_unknown_release_file_rejected(bundle, tmp_path):
    run = tmp_path / "run"
    shutil.copytree(bundle[0], run)
    (run / ".env").write_text("PRIVATE_SENTINEL=not-a-real-key\n")
    release = tmp_path / "release"
    r.build(run, release)
    assert not (release / ".env").exists()
    (release / "unlisted.txt").write_text("extra")
    remanifest(release)
    with pytest.raises(Halted, match="Unexpected"):
        r.verify(release)


def test_partial_recovery_keeps_missing_and_unknown_costs(data, tmp_path):
    run, root = tmp_path / "run", tmp_path / "release"
    report = make_run(run, data, fail_first_two=True)
    assert len(report["recovered"]) == 2
    assert r.build(run, root)["status"] == "incomplete_recovery"
    saved = r._json(root / "recovery_report.json")
    assert saved["remaining_missing"] == [q.TARGETS[0]] and len(saved["attempts"]) == 4
    assert Decimal(saved["new_cost_bound_usd"]) > Decimal(".9")
    assert r._json(root / "recovery_main_analysis.json")["primary_family"]["fixed_family_size"] == 4


def test_pending_call_rejected_without_changing_journal(data, tmp_path):
    run = tmp_path / "run"
    make_run(run, data, pending=True)
    before = (run / "raw/events.jsonl").read_bytes()
    with pytest.raises(Halted):
        r.build(run, tmp_path / "release")
    assert (run / "raw/events.jsonl").read_bytes() == before
    assert not (tmp_path / "release").exists()


def test_launch_prefix_and_funding_tamper_fail(bundle, tmp_path):
    run = tmp_path / "run"
    shutil.copytree(bundle[0], run)
    start = run / "launches" / ("d" * 32) / "start.json"
    value = r._json(start)
    value["preflight"]["kolibri_holdback_usd"] = "0"
    start.write_text(json.dumps(value))
    with pytest.raises(Halted, match="holdbacks"):
        r.build(run, tmp_path / "release")


def test_no_overwrite_or_missing_finish(bundle, tmp_path):
    with pytest.raises(Halted, match="must be new"):
        r.build(bundle[0], bundle[1])
    run = tmp_path / "run"
    shutil.copytree(bundle[0], run)
    (run / "launches" / ("d" * 32) / "finish.json").unlink()
    with pytest.raises(Halted, match="Unclosed"):
        r.build(run, tmp_path / "release")


def test_editorial_and_figure_are_numerically_bound(bundle):
    root = bundle[1]
    values = r._json(root / "evidence/values.json")
    assert values == r._json(root / "figures/figure_data.json")
    for row in values["contrasts"]:
        assert row["planned_blocks"] == 32
    text = (root / "evidence/editorial.md").read_text()
    assert "Qwen3.8" in text and "not the earlier Qwen3.5" in text
    assert "Both primary intervals include zero" in text
    assert "not an equivalence test" in text
    assert (root / "figures/primary_contrasts.pdf").stat().st_size > 1000


def test_no_network_entrypoint_in_exporter():
    source = Path(r.__file__).read_text()
    assert "q.execute(" not in source and "q.recover(" not in source and "ls-remote" not in source


def test_symlink_operational_source_rejected(bundle, tmp_path):
    path = tmp_path / "linked"
    path.symlink_to(bundle[0], target_is_directory=True)
    with pytest.raises(Halted, match="Symlink"):
        r.build(path, tmp_path / "release")
