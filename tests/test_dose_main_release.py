"""Offline export QA: synthetic main records, separate calibration, no dispatch."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import socket

import pytest

from experiments import dose_main_release as r
from tests.test_mapping_scaled_release import synthetic_row, write


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Export tests must never use the network")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture(scope="module")
def real_plan():
    return json.loads((r.p.ROOT / r.p.PLAN).read_text())


def chain(events, plan_hash, ids=()):
    records = []
    for identifier, data in [("binding", {"kind": "binding", "row_ids": sorted(ids)})] + events:
        event = {"id": identifier, "data": data, "seq": len(records), "plan_sha256": plan_hash,
                 "freeze_commit": r.FREEZE, "previous_sha256": records[-1]["sha256"] if records else None}
        event["sha256"] = r.prior._digest(r.p.canonical(event).encode())
        records.append(event)
    return records


def write_chain(path, records):
    path.write_text("".join(r.p.canonical(e) + "\n" for e in records))


@pytest.fixture
def fixture(tmp_path, monkeypatch, real_plan):
    plan = deepcopy(real_plan)
    path = tmp_path / "plan.json"
    write(path, plan)
    original = path.read_bytes()
    def verify_sources(raw, reference):
        r._require(raw == original and reference["freeze_commit"] == r.FREEZE, "Synthetic frozen source mismatch")
        return deepcopy(plan)
    monkeypatch.setattr(r, "_verify_sources", verify_sources)
    monkeypatch.setattr(r.p, "verify_prefix", lambda: None)
    calibration = tmp_path / "prior"
    for spec in r.p.old.inventory():
        if spec["phase"] == "calibration":
            row = synthetic_row(spec, spec["block"] % 2)
            for c in row["coherence"]:
                c["clean_nll"] = .1
            write(calibration / "raw/rows" / (spec["id"] + ".json"), row)
    write(calibration / "raw/failed.json", {"error_type": "TimeoutError", "completed": 205})
    (calibration / "raw/receipts.jsonl").write_bytes(b'{"synthetic_original_journal":true}\r\n')
    write(calibration / "MANIFEST.json", {"synthetic": True})
    monkeypatch.setattr(r.p, "RELEASE", str(calibration))
    monkeypatch.setattr(r.p, "MANIFEST_SHA", r.p.sha(calibration / "MANIFEST.json"))
    monkeypatch.setattr(r, "_prefix_files", lambda: r._files(calibration))
    return plan, path, calibration


@pytest.fixture
def fast_plots(monkeypatch):
    def plots(data, destination):
        destination.mkdir()
        for name in r.FIGURE_FILES:
            (destination / Path(name).name).write_bytes(b"synthetic-offline-figure")
    monkeypatch.setattr(r, "_plots", plots)


def raw_fixture(root, fixture, *, n=480, change=None, qualification=True, pending=False):
    plan, path, _ = fixture
    root.mkdir()
    (root / "PLAN.json").write_bytes(path.read_bytes())
    digest = r.p.sha(path)
    write(root / "runtime.json", {"plan_sha256": digest, "freeze_commit": r.FREEZE})
    write(root / "selection.json", plan["continuation"]["selection"])
    events = [("runtime", {"kind": "runtime"}), ("calibration-prefix", r.analysis.carry_binding(plan)),
              ("selection", {"kind": "selection", "selected_dose": .25, "sha256": r.p.sha(root / "selection.json")})]
    def publish(row):
        rid = row["id"]
        write(root / "rows" / (rid + ".json"), row)
        events.extend([("dispatch:" + rid, {"kind": "dispatch", "row_id": rid}),
            ("row:" + rid, {"kind": "row", "row_id": rid,
             "payload": {"path": "rows/" + rid + ".json", "sha256": r.p.sha(root / "rows" / (rid + ".json"))}})])
    publish({"id": "qualification-live", "result": {"pass": qualification, "zero_hidden_bit_exact": True},
             "judge_fixtures": {"pass": True}, "geometry": {"requested_norm_matched": True}})
    forecast = {**plan["continuation"]["original_throughput"], "available_seconds": 16000, "pass": True}
    write(root / "throughput.json", forecast)
    events.append(("throughput", {"kind": "throughput", "sha256": r.p.sha(root / "throughput.json")}))
    for spec in plan["rows"][:n]:
        row = synthetic_row(spec, spec["block"] % 2)
        for c in row["coherence"]:
            c["clean_nll"] = .1
        if change:
            change(row)
        publish(row)
    if pending:
        rid = plan["rows"][n]["id"]
        events.append(("dispatch:" + rid, {"kind": "dispatch", "row_id": rid}))
        (root / "rows" / (rid + ".pending")).write_text("{}\n")
    if n == 480:
        write(root / "DONE-all.json", {"schema": "dose_exposure_continuation_completion_v1", "pass": True,
            "plan_sha256": digest, "freeze_commit": r.FREEZE, "generations": 480, "calibration_carried": 204,
            "selected_dose": .25, "original_throughput_pass": False})
    else:
        write(root / "failed.json", {"plan_sha256": digest, "error_type": "SyntheticFailure", "completed": n+1})
    write_chain(root / "receipts.jsonl", chain(events, digest, ["qualification-live"] + [s["id"] for s in plan["rows"]]))
    (root / "controller.log").write_bytes(b"Synthetic worker log\r\nPreserve exact bytes\r\n")
    return root


def controller_fixture(root, path, *, recovered=True, closed=True, transform=None):
    digest = r.p.sha(path)
    start = datetime(2026, 10, 5, tzinfo=timezone.utc)
    pod = {"id": "owned-synthetic", "name": "codex-dose-exposure-continuation-20261005-main-012345abcdef", "cost": "6.79"}
    intent = {"payload": {"name": pod["name"]}, "quote": {"hourly_rate_usd": "6.79"}, "blocked": [],
        "created_utc": start.isoformat(), "deadline_utc": (start+timedelta(seconds=r.p.MAIN_SECONDS-r.p.RESERVE_SECONDS)).isoformat(),
        "hard_deadline_utc": (start+timedelta(seconds=r.p.MAIN_SECONDS)).isoformat(),
        "prior_new_usd": "0", "prior_total_usd": r.p.PRIOR_USD, "plan_sha256": digest, "freeze_commit": r.FREEZE}
    events = [("controller:config", {"kind": "main", "namespace": "dose-exposure-continuation-controller",
                "plan_path": r.p.PLAN, "budget": r.p.BUDGET, "hard_seconds": r.p.MAIN_SECONDS}),
              ("create-intent", intent), ("created", pod),
              ("retrieval:final", {"directory": str(root), "pod_id": pod["id"],
                                   "artifacts": {n: r.p.sha(f) for n, f in r._files(root).items()}})]
    if closed:
        cost = Decimal("6.89") * Decimal(1000) / Decimal(3600)
        events += [("delete-intent", {"pod_id": pod["id"], "pod": pod, "retrieval_verified": recovered}),
                   ("closed", {"pod_id": pod["id"], "get_status": 404, "inventory_ids": [],
                    "retrieval_verified": recovered, "artifacts_may_be_unrecovered": not recovered,
                    "utc": (start+timedelta(seconds=1000)).isoformat(), "elapsed_seconds": "1000",
                    "compute_upper_bound_usd": str(cost), "cumulative_upper_bound_usd": str(Decimal(r.p.PRIOR_USD)+cost),
                    "within_limits": True})]
    if transform:
        transform(events)
    records = chain(events, digest)
    receipt, ledger = root.parent / "final-retrieval.json", root.parent / "events.jsonl"
    write(receipt, next(e for e in records if e["id"] == "retrieval:final"))
    write_chain(ledger, records)
    return receipt, ledger


def export(tmp_path, fixture, *, n=480, change=None, **kwargs):
    root = raw_fixture(tmp_path / "retrieved", fixture, n=n, change=change, **kwargs)
    receipt, ledger = controller_fixture(root, fixture[1])
    destination = tmp_path / "release"
    result = r.build(receipt, destination, plan_path=fixture[1], mode="completed" if n == 480 else "partial_technical_failure",
                     controller_ledger=ledger)
    return root, destination, result, receipt, ledger


def test_real_frozen_plan_prefix_and_additive_source_scope(real_plan):
    path = r.p.ROOT / r.p.PLAN
    reference = {"freeze_commit": r.FREEZE, "plan_path": r.p.PLAN, "plan_sha256": r.p.sha(path),
                 "source_hashes": real_plan["source_hashes"], "input_hashes": real_plan["input_hashes"]}
    assert r._verify_sources(path.read_bytes(), reference) == real_plan
    files = r._prefix_files()
    assert len([n for n in files if n.startswith("raw/rows/") and n.endswith(".json")]) == 205
    assert "experiments/dose_main_release.py" not in real_plan["source_hashes"]
    assert "tests/test_dose_main_release.py" not in r.p.source_paths()


def test_complete_export_preserves_two_journals_and_paired_inference(tmp_path, fixture, fast_plots):
    raw, dest, result, receipt, ledger = export(tmp_path, fixture)
    assert result["main_status"] == "completed" and result["lifecycle_verified_this_check"]
    assert (dest / "main/receipts.jsonl").read_bytes() == (raw / "receipts.jsonl").read_bytes()
    assert (dest / "calibration/raw/receipts.jsonl").read_bytes() == (fixture[2] / "raw/receipts.jsonl").read_bytes()
    assert (dest / "main/controller.log").read_bytes().endswith(b"\r\n")
    data = r._json(dest / "FIGURE_DATA.json")
    assert data["display_names"]["notebook"] == "Second rubric"
    for judge in r.JUDGES:
        c = data["contrasts"][judge]
        assert c["target"]["estimate_complete_pairs"] == 0 and c["bootstrap"]["target95"] == [0, 0]
        assert c["main_quality_pass"] and c["verdict"] == "positive_0.30_signature_excluded_at_selected_dose"
        assert c["target"]["n_planned"] == 96
        assert [v["n_planned"] for v in c["control_panels"].values()] == [32]*3
        assert c["specificity"]["panel_weights"] == {str(i): 1/3 for i in (1,2,3)}
    assert sum(c["n"] for c in data["cells"] if c["phase"] == "main") == 480
    assert sum(c["n"] for c in data["cells"] if c["phase"] == "calibration") == 204
    assert not data["original_throughput_pass"]
    assert "\\DoseMainSecondTargetEstimate}{0.000}" in (dest / "values.tex").read_text()
    import re
    macros = re.findall(r"\\newcommand\{\\([^}]+)\}", (dest / "values.tex").read_text())
    assert len(macros) == len(set(macros)) and all(name.isalpha() for name in macros)
    assert r.verify(dest, expected_manifest_sha256=result["manifest_sha256"],
                    controller_receipt=receipt, controller_ledger=ledger)["external_manifest_bound"]


@pytest.mark.parametrize("n,pending,status", [(0,False,"not_run"), (5,False,"incomplete"), (5,True,"incomplete")])
def test_terminal_partial_never_has_main_inference(tmp_path, fixture, fast_plots, n, pending, status):
    _, dest, result, _, _ = export(tmp_path, fixture, n=n, pending=pending)
    assert result["main_status"] == status and not (dest / "analysis/summary.json").exists()
    assert r._json(dest / "FIGURE_DATA.json")["contrasts"] == {}
    assert "TargetEstimate" not in (dest / "values.tex").read_text()
    assert r._json(dest / "REPORT.json")["missing_main_artifacts"] == 480-n


def test_failed_qualification_is_preserved_not_certified(tmp_path, fixture, fast_plots):
    _, dest, _, _, _ = export(tmp_path, fixture, n=0, qualification=False)
    assert r._json(dest / "REPORT.json")["scientific"]["status"] == "not_certified"
    assert all(c["phase"] == "calibration" for c in r._json(dest / "FIGURE_DATA.json")["cells"])


def test_missing_labels_keep_planned_denominator_and_disable_bootstrap(tmp_path, fixture, fast_plots):
    def missing(row):
        if row["spec"]["block"] == 0 and row["spec"]["family"] == "target" and row["spec"]["coefficient"] == -1:
            row["judges"]["notebook"] = {"raw": "unparseable", "label": None}
    _, dest, _, _, _ = export(tmp_path, fixture, change=missing)
    data = r._json(dest / "FIGURE_DATA.json")
    target = data["contrasts"]["notebook"]["target"]
    assert target["n_planned"] == 96 and target["missing_pairs"] == 1
    assert target["identification_bounds"] == [0, 1/96]
    assert data["contrasts"]["notebook"]["bootstrap"]["status"] == "not_reported_missing_labels"


def test_quality_failure_remains_failed_without_fallback(tmp_path, fixture, fast_plots):
    def capped(row):
        row["turns"][0]["cap_hit"] = True
        if row["spec"]["family"] == "target":
            row["turns"][1]["cap_hit"] = True
    _, dest, _, _, _ = export(tmp_path, fixture, change=capped)
    data = r._json(dest / "FIGURE_DATA.json")
    assert all(v["verdict"] == "main_quality_failed_no_fallback" for v in data["contrasts"].values())
    assert all(c["quality_flagged"] == 0 for c in data["cells"] if c["phase"] == "main" and c["group"] == "zero")


@pytest.mark.parametrize("closed,recovered", [(False,True), (True,False)])
def test_complete_requires_retrieval_and_deletion(tmp_path, fixture, closed, recovered):
    raw = raw_fixture(tmp_path / "retrieved", fixture)
    receipt, ledger = controller_fixture(raw, fixture[1], closed=closed, recovered=recovered)
    with pytest.raises(ValueError, match="verified retrieval"):
        r.build(receipt, tmp_path / "release", plan_path=fixture[1], controller_ledger=ledger)


def test_partial_cannot_be_presented_as_complete(tmp_path, fixture):
    raw = raw_fixture(tmp_path / "retrieved", fixture, n=5)
    receipt, ledger = controller_fixture(raw, fixture[1])
    with pytest.raises(ValueError, match="480"):
        r.build(receipt, tmp_path / "release", plan_path=fixture[1], controller_ledger=ledger)


@pytest.mark.parametrize("field,value", [("prior_total_usd", "0"), ("prior_new_usd", "0.1609895469")])
def test_carry_cannot_reset_or_double_count_cheap(tmp_path, fixture, field, value):
    raw = raw_fixture(tmp_path / "retrieved", fixture, n=0)
    def mutate(events):
        next(data for name, data in events if name == "create-intent")[field] = value
    receipt, ledger = controller_fixture(raw, fixture[1], transform=mutate)
    with pytest.raises(ValueError, match="carry|double-counted"):
        r.build(receipt, tmp_path / "release", plan_path=fixture[1], mode="partial_technical_failure", controller_ledger=ledger)


@pytest.mark.parametrize("name", ["tokens.env", "weights.safetensors", "id_ed25519", "other.json"])
def test_public_inventory_rejects_unapproved_files(tmp_path, fixture, name):
    raw = raw_fixture(tmp_path / "retrieved", fixture, n=0)
    (raw / name).write_text("not public")
    with pytest.raises(ValueError, match="Unapproved"):
        r.build(raw, tmp_path / "release", plan_path=fixture[1], mode="partial_technical_failure")


def rehash(dest):
    manifest = r._json(dest / "MANIFEST.json")
    files = r._files(dest)
    files.pop("MANIFEST.json")
    manifest["files"] = r._entries(files)
    write(dest / "MANIFEST.json", manifest)


@pytest.mark.parametrize("name", ["calibration/raw/failed.json", "main/rows/qualification-live.json", "REPORT.json",
                                 "FIGURE_DATA.json", "RESULTS.md", "values.tex", "figures/main_rates.png"])
def test_rehash_cannot_hide_artifact_tampering(tmp_path, fixture, fast_plots, name):
    _, dest, _, _, _ = export(tmp_path, fixture, n=5)
    path = dest / name
    if path.suffix == ".json":
        value = r._json(path); value["tampered"] = True; write(path, value)
    else:
        path.write_bytes(path.read_bytes() + b"tampered")
    rehash(dest)
    with pytest.raises(ValueError):
        r.verify(dest)


def test_new_real_figures_are_nonblank_and_use_display_labels(tmp_path, fixture, monkeypatch):
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure
    from matplotlib.text import Text
    rendered, intervals, horizontal = [], [], []
    original = Text.set_text
    def capture(self, text):
        rendered.append(str(text))
        return original(self, text)
    monkeypatch.setattr(Text, "set_text", capture)
    original_save = Figure.savefig
    def save(self, *args, **kwargs):
        assert not self.texts and self._suptitle is None
        self.canvas.draw()
        name = Path(args[0]).stem
        geometry = (2, 2) if name.endswith("quality") else (2, 1)
        assert self.get_figwidth() == pytest.approx(6.8)
        assert all(ax.get_subplotspec().get_gridspec().get_geometry() == geometry for ax in self.axes)
        frame = self.get_window_extent()
        renderer = self.canvas.get_renderer()
        texts = [text for legend in self.legends for text in legend.get_texts()]
        for ax in self.axes:
            texts.extend([ax.xaxis.label, ax.yaxis.label, ax.title, ax._left_title, *ax.texts])
            # Matplotlib allocates tick labels outside the view but does not draw them.
            texts.extend(t for t in ax.get_xticklabels() if min(ax.get_xlim()) <= t.get_position()[0] <= max(ax.get_xlim()))
            texts.extend(t for t in ax.get_yticklabels() if min(ax.get_ylim()) <= t.get_position()[1] <= max(ax.get_ylim()))
        for text in texts:
            if not text.get_visible() or not text.get_text():
                continue
            assert text.get_fontsize() >= 9.5
            box = text.get_window_extent(renderer)
            assert box.x0 >= frame.x0 - 1 and box.y0 >= frame.y0 - 1, (name, text.get_text())
            assert box.x1 <= frame.x1 + 1 and box.y1 <= frame.y1 + 1, (name, text.get_text())
        for ax in self.axes:
            for line in ax.lines:
                if line.get_marker() in {"|", "_"}:
                    assert line.get_markersize() >= 6
                elif line.get_marker() in {"o", "s", "^", "D"}:
                    assert line.get_markersize() <= 4 and line.get_markerfacecolor() == "white"
            if name == "main_rates":
                counts = [t.get_window_extent(renderer) for t in ax.texts if "\n" not in t.get_text()]
                assert all(box.x0 > ax.get_window_extent().x1 for box in counts)
                assert all(not a.overlaps(b) for i, a in enumerate(counts) for b in counts[i+1:])
        return original_save(self, *args, **kwargs)
    monkeypatch.setattr(Figure, "savefig", save)
    original_lines = Axes.vlines
    def limits(self, x, ymin, ymax, *args, **kwargs):
        intervals.extend(zip(x, ymin, ymax))
        return original_lines(self, x, ymin, ymax, *args, **kwargs)
    monkeypatch.setattr(Axes, "vlines", limits)
    original_horizontal = Axes.hlines
    def horizontal_limits(self, y, xmin, xmax, *args, **kwargs):
        horizontal.append((y, xmin, xmax))
        return original_horizontal(self, y, xmin, xmax, *args, **kwargs)
    monkeypatch.setattr(Axes, "hlines", horizontal_limits)
    _, dest, _, _, _ = export(tmp_path, fixture)
    from PIL import Image, ImageStat
    for name in r.FIGURES:
        with Image.open(dest / "figures" / (name + ".png")) as image:
            assert image.width >= 1000 and image.height >= 600
            assert min(ImageStat.Stat(image.convert("RGB")).stddev) > 10
    text = "\n".join(rendered)
    assert "notebook" not in text.lower()
    assert "Second rubric (primary)" in text and "Paper rubric (secondary)" in text
    assert "Quality PASS" not in text and "original calibration" not in text
    data = r._json(dest / "FIGURE_DATA.json")
    expected = [(c["dose"]*c["sign"], *c["labels"][judge]["marginal_cp_bounds"])
                for c in data["cells"] if c["phase"] == "calibration" for judge in r.JUDGES]
    assert sorted(intervals) == sorted(expected * 2)  # Build and read-only verification.
    expected_horizontal = []
    for judge, result in data["contrasts"].items():
        values = [result["target"], *result["control_panels"].values(), result["specificity"]]
        expected_horizontal.extend((i, *value["bounds"]) for i, value in enumerate(values))
        cells = sorted((c for c in data["cells"] if c["phase"] == "main"),
                       key=lambda c: (r.GROUPS.index(c["group"]), c["sign"]))
        expected_horizontal.extend((i, *c["labels"][judge]["marginal_cp_bounds"]) for i, c in enumerate(cells))
    assert sorted(horizontal) == sorted(expected_horizontal * 2)
    assert data["figure_captions"] == r.FIGURE_CAPTIONS
    results = (dest / "RESULTS.md").read_text()
    assert all(caption in results for caption in r.FIGURE_CAPTIONS.values())


def test_known_positive_truth_keeps_sign_and_fixed_panel_weights(tmp_path, fixture, fast_plots):
    def truth(row):
        positive = int(row["spec"]["family"] == "target" and row["spec"]["coefficient"] == -1)
        row["judges"] = {"notebook": {"label": positive, "raw": "yes" if positive else "no"},
                         "paper": {"label": positive, "raw": str(positive)}}
    _, dest, _, _, _ = export(tmp_path, fixture, change=truth)
    for result in r._json(dest / "FIGURE_DATA.json")["contrasts"].values():
        assert result["target"]["estimate_complete_pairs"] == 1
        assert result["specificity"]["estimate_complete_pairs"] == 1
        assert all(panel["estimate_complete_pairs"] == 0 for panel in result["control_panels"].values())
        assert result["verdict"] == "large_positive_specific_effect"


@pytest.mark.parametrize("field,value", [("cumulative_upper_bound_usd", "1"), ("get_status", 200),
                                       ("inventory_ids", ["owned-synthetic"]), ("within_limits", False)])
def test_closed_cost_and_direct_deletion_claims_checked(tmp_path, fixture, field, value):
    raw = raw_fixture(tmp_path / "retrieved", fixture)
    def mutate(events):
        next(data for name, data in events if name == "closed")[field] = value
    receipt, ledger = controller_fixture(raw, fixture[1], transform=mutate)
    with pytest.raises(ValueError):
        r.build(receipt, tmp_path / "release", plan_path=fixture[1], controller_ledger=ledger)
