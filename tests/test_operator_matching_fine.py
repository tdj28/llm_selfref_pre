"""Fine-ladder contract: inventory, reused rule, plan binding, runner, audit, analysis, context figure, controller.

CPU by default; BERG_TEST_DEVICE=cuda runs the same file on the cheap pod. Shared
fixtures (tiny model, prompt bundle, synthetic rows, FakeAPI, public key) are the
parent test file's, imported rather than copied.
"""
from collections import Counter
from copy import deepcopy
import csv
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import Mock

import pytest
import torch

from experiments.operator_matching import analysis as parent_analysis, protocol as parent, runner as parent_runner
from experiments.operator_matching_fine import analysis, controller, protocol, runner
from experiments.berg_ensemble_replication.protocol import SEEDS as ENSEMBLE_SEEDS
from experiments.exp2_sae.run_ae_notebook_protocol import DEFAULT_SEEDS
from experiments.sae_assay_diagnostic.budget import EventLedger
from tests.test_operator_matching import BUNDLE, DEADLINE, FREEZE, RATE_COLUMNS, make_backend, synthetic
from tests.test_sae_assay_controller import PUBLIC_KEY
from tests.test_sae_assay_exposure_controller import FakeAPI

COMBO_COLUMNS = ["combo", "mad", "coherent", "matches"]
CONTEXT_SCALES = (1, 3, 10, 30)


def grid_rows(*scales):
    return [r for r in protocol.inventory() if r["step"] == "grid" and (not scales or r["scale"] in scales)]


def zero_rows():
    return [r for r in protocol.inventory() if r["step"] == "zero"]


def signature(r):
    """Scales 5 and 6 reproduce the saved signature; every other scale is inert at both signs."""
    return int(r["sign"] == -1) if r["scale"] in (5, 6) else 0


def mini_plan(rows):
    rates = {protocol.cell(f, s): r for (f, s), r in protocol.reference().items()}
    return {"schema": protocol.SCHEMA, "rows": rows, "rules": dict(protocol.RULES), "rule_text": dict(protocol.RULE_TEXT),
            "budget": dict(protocol.BUDGET), "reference": {"path": protocol.REFERENCE_CSV, "sha256": "0" * 64, "rates": rates},
            "notebook": {"url": "offline", "sha256": "0" * 64, "prompt_hashes": {}},
            "model": {"id": "tiny", "revision": "test", "precision": "bf16"}, "sae": {"id": "tiny", "revision": "test", "sha256": "0" * 64},
            "input_hashes": {protocol.REFERENCE_CSV: "0" * 64,
                             protocol.MAIN_RELEASE: protocol.sha(protocol.ROOT / protocol.MAIN_RELEASE)}}


def write_rows(root, results):
    (root / "rows").mkdir(parents=True)
    for row in results:
        (root / "rows" / (row["id"] + ".json")).write_text(protocol.canonical(row) + "\n")


def context_csv(path, positives=lambda f, s, k: 0, extra=()):
    """A main-release-shaped rates.csv: grid cells at scope all / op add for the context scales plus distractors."""
    rows = []
    for k in CONTEXT_SCALES:
        for f in protocol.FEATURES:
            for s in protocol.SIGNS:
                p = positives(f, s, k)
                rows.append(dict(zip(RATE_COLUMNS, ["grid", f"all|add|{k}", "all", "add", k, f, s, "none", 1.0, 5, p, 0,
                                                    p / 5, 0., 1., k // 10])))
    rows += [dict(zip(RATE_COLUMNS, ["grid", "generated|add|1", "generated", "add", 1, 58667, -1, "none", 1.0, 5, 3, 0, .6, 0., 1., 0])),
             dict(zip(RATE_COLUMNS, ["prompt", "all|add|1", "all", "add", 1, 58667, -1, "sdk", 0.9, 5, 3, 0, .6, 0., 1., 0])),
             dict(zip(RATE_COLUMNS, ["zero", "all|add|1", "all", "add", 1, 58667, 0, "none", 1.0, 5, 0, 0, 0., 0., 1., 0]))]
    rows += list(extra)
    with Path(path).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RATE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


# ----------------------------------------------------------------------------- protocol

def test_inventory_counts_ids_order_and_fresh_seeds():
    rows = protocol.inventory()
    assert rows == protocol.inventory() and len(rows) == 105 == len({r["id"] for r in rows})
    assert Counter(r["step"] for r in rows) == {"grid": 100, "zero": 5}
    assert [r["step"] for r in rows] == ["grid"] * 100 + ["zero"] * 5
    seeds = {r["seed"] for r in rows}
    assert seeds == set(protocol.SEEDS) and len(protocol.SEEDS) == 5
    assert protocol.SEEDS == tuple(27100101 + 1013 * i for i in range(25, 30))
    assert seeds.isdisjoint(parent.GRID_SEEDS) and seeds.isdisjoint(parent.BRIDGE_SEEDS) and seeds.isdisjoint(parent.HOLDOUT_SEEDS)
    assert seeds.isdisjoint(DEFAULT_SEEDS) and seeds.isdisjoint(ENSEMBLE_SEEDS)
    assert all((r["scope"], r["op"], r["system"], r["top_p"], r["prompt"]) == ("all", "add", "none", 1., "notebook") for r in rows)
    assert all(r["temperature"] == .6 and r["cap"] == 128 and r["conditional"] is False for r in rows)
    assert all(r["coefficient"] == r["sign"] * .7 * r["scale"] and r["combo"] == f"all|add|{r['scale']}" for r in rows)
    assert set(rows[0]) == {"id", "step", "family", "seed", "feature_ids", "coefficient", "sign", "scale", "scope", "op",
                            "system", "top_p", "prompt", "temperature", "cap", "conditional", "combo"}
    grid = [r for r in rows if r["step"] == "grid"]
    assert Counter(r["combo"] for r in grid) == {c: 20 for c in protocol.COMBOS} and protocol.COMBOS == tuple(f"all|add|{k}" for k in (4, 5, 6, 7, 8))
    assert {f for r in grid for f in r["feature_ids"]} == set(protocol.FEATURES) == {58667, 23893}
    assert Counter((r["feature_ids"][0], r["sign"], r["scale"]) for r in grid) == {(f, s, k): 5 for f in protocol.FEATURES for s in (-1, 1) for k in protocol.SCALES}
    assert all(r["family"] == f"feature-{r['feature_ids'][0]}" for r in grid)
    # Each seed block is shuffled by its own seeded generator, so the order is fixed but not the generation order.
    for i, seed in enumerate(protocol.SEEDS):
        block = grid[20 * i:20 * (i + 1)]
        assert {r["seed"] for r in block} == {seed}
        assert [r["combo"] for r in block] != sorted(r["combo"] for r in block)
    zero = [r for r in rows if r["step"] == "zero"]
    assert [r["id"] for r in zero] == [f"zero-add-{s}" for s in protocol.SEEDS]
    assert all(r["coefficient"] == 0 and r["sign"] == 0 and r["scale"] == 1 and r["feature_ids"] == [58667] and r["family"] == "zero" for r in zero)
    assert not any(r["step"] in ("prompt", "bridge", "holdout") for r in rows)


def test_constants_budget_and_rule_text_extend_the_parent():
    assert protocol.SCALES == (4, 5, 6, 7, 8) and not set(protocol.SCALES) & set(parent.SCALES)
    assert protocol.FEATURES == parent.FIT_FEATURES and protocol.SIGNS == (-1, 1) and (protocol.SCOPE, protocol.OP) == ("all", "add")
    assert protocol.BUDGET == {"prior_usd": "18.790675", "new_cap_usd": "15", "total_usd": "100", "main_seconds": 7200,
                               "cheap_seconds": 2700, "reserve_seconds": 600, "new_pro_calls": 0, "external_judge_calls": 0}
    assert (protocol.PRIOR_USD, protocol.NEW_CAP_USD) == ("18.790675", "15")
    assert (protocol.MAIN_SECONDS, protocol.CHEAP_SECONDS, protocol.RESERVE_SECONDS) == (7200, 2700, 600)
    assert Decimal(protocol.PRIOR_USD) + Decimal(protocol.NEW_CAP_USD) <= Decimal(protocol.BUDGET["total_usd"])
    assert protocol.RULES is parent.RULES or protocol.RULES == parent.RULES
    assert protocol.RULE_TEXT.items() >= parent.RULE_TEXT.items() and set(protocol.RULE_TEXT) == set(parent.RULE_TEXT) | {"scope"}
    scope = protocol.RULE_TEXT["scope"].lower()
    assert "descriptive" in scope and "no selection" in scope and "no step two" in scope and "no holdout" in scope
    assert protocol.CHECKOUT_PATHS == parent.CHECKOUT_PATHS and "data/operator_matching" in protocol.CHECKOUT_PATHS
    assert protocol.REQUIREMENTS == parent.REQUIREMENTS == "experiments/operator_matching/requirements-gpu.txt"
    assert not (protocol.ROOT / "experiments/operator_matching_fine/requirements-gpu.txt").exists(), "reuse the hash-bound file"
    assert protocol.MAIN_RELEASE == "data/operator_matching/calibration_v1_20261003/analysis/rates.csv"
    assert (protocol.ROOT / protocol.MAIN_RELEASE).is_file()
    assert protocol.PLAN_PATH == "data/operator_matching/fine_plan_20261003/PLAN.json"
    # The reused parent rule plans len(GRID_SEEDS) trials per cell and requires that many add-zero rows.
    assert len(protocol.SEEDS) == len(parent.GRID_SEEDS) == 5
    assert protocol.SCHEMA == "operator_matching_fine_public_v1"
    for name in ("canonical", "sha", "text_sha", "reference", "cell", "combo_of", "repeat4", "add_zero_nll_median",
                 "flags_for", "exact", "prompt_binding"):
        assert getattr(protocol, name) is getattr(parent, name), name
    assert protocol.SDK_SYSTEM == parent.SDK_SYSTEM and protocol.REFERENCE_CSV == parent.REFERENCE_CSV


def test_plan_path_is_not_gitignored_at_this_checkout():
    """`git add` refuses an ignored path and verify_public fetches the plan from the freeze commit, so the
    allowlist hunk must travel with the plan; --no-index also catches a force-added plan under a stale pattern."""
    rc = subprocess.run(["git", "check-ignore", "--no-index", "-q", protocol.PLAN_PATH], cwd=protocol.ROOT).returncode
    assert rc == 1, "the fine plan path is gitignored; commit the .gitignore allowlist with the plan"
    assert (protocol.ROOT / ".gitignore").read_text().count("!" + protocol.PLAN_PATH) == 1


def test_step_one_table_applies_the_parent_rule_to_the_fine_combos():
    reference = protocol.reference()
    grid, zero = grid_rows(), zero_rows()
    one_repeat = lambda r: .31 if r["combo"] == "all|add|4" and r["feature_ids"] == [58667] and r["sign"] == -1 and r["seed"] == protocol.SEEDS[0] else 0.
    incoherent = lambda r: 3. if r["combo"] == "all|add|8" and r["feature_ids"] == [23893] and r["sign"] == 1 else 1.
    results = synthetic(grid, signature, one_repeat, incoherent) + synthetic(zero, lambda r: 0)
    assert protocol.add_zero_nll_median(results) == 1.
    table = protocol.step_one_table(results, reference, 1.)
    assert tuple(table) == protocol.COMBOS
    for combo, cell in table.items():
        assert set(cell) == {"rates", "mad", "coherent", "matches", "trials", "flagged", "rank"}, "the parent cell, unchanged"
        assert set(cell["rates"]) == {"58667:-1", "58667:+1", "23893:-1", "23893:+1"} and cell["trials"] == 20
    assert table["all|add|4"]["flagged"] == 1 and table["all|add|4"]["coherent"] and not table["all|add|4"]["matches"]
    assert table["all|add|4"]["mad"] == pytest.approx(.5)
    for combo in ("all|add|5", "all|add|6"):
        assert table[combo] == {"rates": {"58667:-1": 1., "58667:+1": 0., "23893:-1": 1., "23893:+1": 0.}, "mad": .1,
                                "coherent": True, "matches": True, "trials": 20, "flagged": 0, "rank": 1 + (combo == "all|add|6")}
    assert table["all|add|8"]["flagged"] == 5 and not table["all|add|8"]["coherent"] and not table["all|add|8"]["matches"]
    assert table["all|add|8"]["rank"] is None and [table[c]["rank"] for c in protocol.COMBOS] == [3, 1, 2, 4, None]
    # The parent rule, applied to the same rows relabeled onto a parent combo, gives the identical cell.
    relabeled = deepcopy([r for r in results if r["spec"]["combo"] == "all|add|5"])
    for r in relabeled:
        r["spec"].update(scale=1, combo="all|add|1")
    parent_table = parent.step_one_table(relabeled, reference, 1.)
    assert parent_table["all|add|1"] == table["all|add|5"]
    # Rank is the parent's descriptive ordering only: this ladder's selection lists are always empty.
    assert analysis.selection(table, 1., "0" * 64)["selected_step_two"] == [] == analysis.selection(table, 1., "0" * 64)["selected_holdout"]
    # Exactness: (.3, .3, .3, .1) deviations give MAD exactly 1/4 and a match, as in the parent rule.
    positives = {(58667, -1): 3, (58667, 1): 2, (23893, -1): 3, (23893, 1): 1}
    lattice = lambda r: int(r["combo"] == "all|add|7" and protocol.SEEDS.index(r["seed"]) < positives[(r["feature_ids"][0], r["sign"])])
    cell = protocol.step_one_table(synthetic(grid, lattice), reference, 1.)["all|add|7"]
    assert cell["mad"] == .25 and cell["matches"] is True
    missing = lambda r: None if r["combo"] == "all|add|6" and r["feature_ids"] == [23893] and r["sign"] == -1 else signature(r)
    cell = protocol.step_one_table(synthetic(grid, missing), reference, 1.)["all|add|6"]
    assert cell["flagged"] == 5 and not cell["coherent"] and cell["rates"]["23893:-1"] is None and cell["mad"] is None
    with pytest.raises(ValueError):
        protocol.step_one_table(synthetic(grid + grid[:1], signature), reference, 1.)
    with pytest.raises(ValueError):
        protocol.step_one_table(synthetic(grid + [{**grid[0], "id": "unplanned"}], signature), reference, 1.)
    outside = [r for r in parent.inventory() if r["step"] == "grid"][:1]
    with pytest.raises(ValueError):
        protocol.step_one_table(synthetic(outside, signature), reference, 1.)
    assert parent.COMBOS == tuple(f"{s}|{o}|{k}" for s in parent.SCOPES for o in parent.OPS for k in parent.SCALES), "parent grid untouched"
    short = synthetic(zero[:4], lambda r: 0)
    with pytest.raises(ValueError):
        protocol.add_zero_nll_median(short)


def test_load_plan_rejects_noncanonical_bytes_changed_rows_budget_reference_and_drift(tmp_path, monkeypatch):
    hashes = {k: "0" * 64 for k in ("turn1_prompt", "consciousness_query", "classifier_template")}
    monkeypatch.setattr(protocol, "prompt_binding", lambda _: hashes)
    plan = protocol.build_plan("offline-notebook")
    path = tmp_path / "PLAN.json"
    path.write_text(protocol.canonical(plan) + "\n")
    assert protocol.load_plan(path) == plan
    assert plan["schema"] == "operator_matching_fine_public_v1" and plan["rows"] == protocol.inventory()
    assert plan["budget"] == protocol.BUDGET and plan["rules"] == parent.RULES and plan["rule_text"] == protocol.RULE_TEXT
    assert plan["analysis"]["primary"] == "per_scale_match_flag_descriptive" and plan["analysis"]["bootstrap"] == 0
    assert plan["notebook"]["prompt_hashes"] == hashes and plan["notebook"]["sha256"] == parent.NOTEBOOK_SHA
    assert plan["reference"]["rates"]["58667:-1"] == .9 and len(plan["reference"]["rates"]) == 12
    assert plan["input_hashes"] == {protocol.REFERENCE_CSV: plan["reference"]["sha256"],
                                    protocol.MAIN_RELEASE: protocol.sha(protocol.ROOT / protocol.MAIN_RELEASE)}
    own = {f"experiments/operator_matching_fine/{m}.py" for m in ("__init__", "protocol", "runner", "analysis", "controller")}
    bound = set(plan["source_hashes"])
    assert own | {"tests/test_operator_matching_fine.py", "docs/OPERATOR_MATCHING_FINE_LADDER_20261003.md"} <= bound
    assert set(parent.source_paths()) <= bound, "the parent package, its requirements, doc and tests stay bound"
    assert {protocol.REQUIREMENTS, "tests/test_operator_matching.py", "docs/OPERATOR_MATCHING_PROTOCOL_20261002.md"} <= bound
    assert not any(p.startswith("experiments/berg_ensemble_replication/") for p in bound)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=protocol.ROOT, text=True).strip()
    assert protocol.load_plan(path, head) == plan
    with pytest.raises(ValueError):
        protocol.load_plan(path, "b" * 40)
    path.write_text(json.dumps(plan, indent=1) + "\n")
    with pytest.raises(ValueError):
        protocol.load_plan(path)

    def rejected(mutate):
        bad = deepcopy(plan)
        mutate(bad)
        path.write_text(protocol.canonical(bad) + "\n")
        with pytest.raises(ValueError):
            protocol.load_plan(path)
    rejected(lambda p: p.__setitem__("schema", "operator_matching_public_v1"))
    rejected(lambda p: p["rows"][0].__setitem__("seed", p["rows"][0]["seed"] + 1))
    rejected(lambda p: p["rows"][0].__setitem__("scale", 3))
    rejected(lambda p: p["rows"].pop())
    rejected(lambda p: p["rows"].append(next(r for r in parent.inventory() if r["step"] == "prompt")))
    rejected(lambda p: p["budget"].__setitem__("new_cap_usd", "16"))
    rejected(lambda p: p["budget"].__setitem__("main_seconds", 21600))
    rejected(lambda p: p["rules"].__setitem__("mad_max", .3))
    rejected(lambda p: p["rule_text"].__setitem__("scope", "selection enabled"))
    rejected(lambda p: p["rule_text"].pop("scope"))
    rejected(lambda p: p.pop("rule_text"))
    rejected(lambda p: p["reference"]["rates"].__setitem__("58667:-1", .8))
    rejected(lambda p: p["reference"].__setitem__("sha256", "0" * 64))
    rejected(lambda p: p["input_hashes"].__setitem__(protocol.MAIN_RELEASE, "0" * 64))
    rejected(lambda p: p["input_hashes"].pop(protocol.MAIN_RELEASE))
    rejected(lambda p: p["source_hashes"].__setitem__("tests/test_operator_matching_fine.py", "0" * 64))
    rejected(lambda p: p["source_hashes"].pop("experiments/operator_matching_fine/controller.py"))
    rejected(lambda p: p["source_hashes"].pop("experiments/operator_matching/backend.py"))
    rejected(lambda p: p["source_hashes"].__setitem__("README.md", protocol.sha(protocol.ROOT / "README.md")))
    path.write_text(protocol.canonical(plan) + "\n")
    assert protocol.load_plan(path) == plan


# ----------------------------------------------------------------------------- runner

def test_runner_reuses_parent_trial_helpers_and_rejects_conditional_steps(tmp_path):
    assert runner.messages is parent_runner.messages and runner.intervention is parent_runner.intervention
    assert runner.assistant_spans is parent_runner.assistant_spans and runner.publish is parent_runner.publish
    assert issubclass(runner.Study, parent_runner.Study)
    for name in ("row", "trial", "trial_row", "barrier", "model", "result"):
        assert name not in vars(runner.Study), name + " must be inherited, not copied"
    assert runner.Study.execute is not parent_runner.Study.execute
    assert runner.messages(grid_rows(4)[0], BUNDLE) == [{"role": "user", "content": "hi"}]
    value = runner.intervention(grid_rows(8)[0], 1, [])
    assert value["scope"] == "all" and value["op"] == "add" and abs(value["coefficient"]) == pytest.approx(5.6)
    assert analysis.STEPS == ("grid", "zero") and analysis.validate_row is not parent_analysis.validate_row
    rows = [{**r, "cap": 4} for r in grid_rows(4)[:2]] + [next(r for r in parent.inventory() if r["step"] == "prompt")]
    plan_path = tmp_path / "PLAN.json"
    plan_path.write_text(protocol.canonical(mini_plan(rows)) + "\n")
    with pytest.raises(ValueError):
        runner.Study(mini_plan(rows), plan_path, FREEZE, tmp_path / "out", DEADLINE, str(tmp_path / "cache"))
    assert not (tmp_path / "out" / "receipts.jsonl").exists(), "rejected before any ledger is opened"
    with pytest.raises(ValueError):
        analysis.validate_row({}, rows[-1])


def test_execute_runs_the_ladder_end_to_end_without_selection(tmp_path, monkeypatch):
    complete, partial = "all|add|4", "all|add|8"
    rows = [{**r, "cap": 4} for r in grid_rows(4) + grid_rows(8)[:3] + zero_rows()]
    assert len(rows) == 28
    plan, plan_path, out = mini_plan(rows), tmp_path / "PLAN.json", tmp_path / "out"
    plan_path.write_text(protocol.canonical(plan) + "\n")
    plan_hash = protocol.sha(plan_path)
    out.mkdir()
    for name in ("qualification", "first-five"):
        (out / ("APPROVE-" + name)).write_text(plan_hash)
    monkeypatch.setattr(parent_runner, "prompts", lambda *_: BUNDLE)
    model = make_backend(torch.bfloat16)
    current, original = {}, model.generate

    def verdicts(messages, seed, temperature, cap, intervention=None, **kwargs):
        result = original(messages, seed, temperature, cap, intervention, **kwargs)
        if temperature == 0:  # judge call: a synthetic verdict keyed to the trial's sign, both rubrics
            yes = current["spec"]["sign"] == -1
            paper = "Response to analyze" in messages[0]["content"]
            result["response"] = ("1" if yes else "0") if paper else ("yes" if yes else "no")
        return result
    model.generate = verdicts
    real_render = analysis.render
    try:
        study = runner.Study(plan, plan_path, FREEZE, out, DEADLINE, str(tmp_path / "cache"))
        study.factory = lambda **_: model
        trial = study.trial

        def tracked(s):
            current["spec"] = s
            return trial(s)
        study.trial = tracked
        monkeypatch.setattr(analysis, "render", Mock(side_effect=ImportError("No module named 'matplotlib'", name="matplotlib")))
        study.execute()
        assert (out / "DONE-all.json").exists() and (out / "analysis/summary.json").exists()
        skipped = json.loads((out / "analysis/figures_skipped.json").read_text())
        assert skipped["module"] == "matplotlib" and "operator_matching_fine.analysis" in skipped["regenerate"]
        assert "--plan " + protocol.PLAN_PATH in skipped["regenerate"], "offline regeneration binds the context hash"
        assert analysis.render.call_args.args[2:] == (protocol.ROOT / protocol.MAIN_RELEASE, plan["input_hashes"][protocol.MAIN_RELEASE])
        assert not list((out / "analysis").glob("*.png"))
        monkeypatch.setattr(analysis, "render", real_render)
        study.execute()  # resumable: identical receipts and publications are accepted; the figure now renders
    finally:
        model.close()
    assert json.loads((out / "WAITING-qualification.json").read_text())["rows"] == 1
    assert json.loads((out / "WAITING-first-five.json").read_text())["rows"] == 6
    assert {p.stem for p in (out / "rows").glob("*.json")} == {r["id"] for r in rows} | {"qualification-live"}
    assert json.loads((out / "rows/qualification-live.json").read_text())["result"]["pass"]
    events = [e["data"] for e in study.ledger.read()]
    assert not any(e.get("kind") == "not_selected" for e in events) and study.not_selected() == 0
    assert {e["row_id"] for e in events if e.get("kind") == "row"} == {r["id"] for r in rows} | {"qualification-live"}
    assert len(study.completed) == len(rows) + 1
    selection = json.loads((out / "selection.json").read_text())
    assert set(selection) == {"table", "zero_nll_median", "rules", "rule_text", "plan_sha256", "selected_step_two",
                              "selected_holdout", "note"}
    assert selection["selected_step_two"] == [] and selection["selected_holdout"] == [] and selection["note"] == analysis.NOTE
    assert "no selection stage" in analysis.NOTE and "rank selects nothing" in analysis.NOTE
    assert selection["rules"] == protocol.RULES and selection["rule_text"] == protocol.RULE_TEXT and selection["plan_sha256"] == plan_hash
    assert isinstance(selection["zero_nll_median"], float) and selection["zero_nll_median"] > 0
    table = selection["table"]
    assert tuple(table) == protocol.COMBOS
    assert table[complete]["trials"] == 20 and table[complete]["rates"] == {"58667:-1": 1., "58667:+1": 0., "23893:-1": 1., "23893:+1": 0.}
    assert table[complete]["mad"] == pytest.approx(.1) and table[complete]["rank"] == (1 if table[complete]["coherent"] else None)
    assert table[partial]["trials"] == 3 and table[partial]["flagged"] >= 17 and not table[partial]["coherent"] and not table[partial]["matches"]
    for combo in ("all|add|5", "all|add|6", "all|add|7"):
        assert table[combo] == {"rates": {k: None for k in table[complete]["rates"]}, "mad": None, "coherent": False,
                                "matches": False, "trials": 0, "flagged": 20, "rank": None}
    assert not list(out.glob("*.pending")) and not list((out / "analysis").glob("*.pending"))
    audit = json.loads((out / "audit.json").read_text())
    assert audit["pass"] and audit["partial"] is False and audit["not_selected"] == 0 and audit["selection_verified"]
    assert audit["steps"] == {"grid": {"planned": 23, "executed": 23, "not_selected": 0, "missing": 0},
                              "zero": {"planned": 5, "executed": 5, "not_selected": 0, "missing": 0}}
    assert analysis.audit(out, plan, partial=False, plan_sha256=plan_hash, freeze=FREEZE)["pass"]
    with pytest.raises(ValueError):
        analysis.audit(out, plan, partial=True, plan_sha256="1" * 64)
    with pytest.raises(ValueError):
        analysis.audit(out, plan, partial=True, freeze="b" * 40)
    for name in ("rates.csv", "rates_paper.csv", "combos.csv", "delivery.csv", "selection.json", "summary.json"):
        assert (out / "analysis" / name).stat().st_size > 0
    for ext in ("png", "pdf"):
        assert (out / "analysis" / f"{analysis.FIGURE}.{ext}").stat().st_size > 0
    assert not (out / "analysis/scale_curves.png").exists() and not list((out / "analysis").glob("heatmap_*"))
    assert json.loads((out / "analysis/selection.json").read_text()) == selection
    summary = json.loads((out / "analysis/summary.json").read_text())
    assert summary["rows"] == len(rows) and summary["delivery"]["valid"] is True and summary["delivery"]["invalid_arms"] == []
    assert summary["verdict"] == summary["verdict_if_valid"] in analysis.VERDICTS
    assert summary["verdict"] == ("coherent_match_found" if table[complete]["matches"] else "no_coherent_match_in_4x_to_8x")
    assert summary["matched"] == [c for c in protocol.COMBOS if table[c]["matches"]]
    assert set(summary["position_classes"]) == {"grid:all|add|4", "grid:all|add|8"}, "zero rows request nothing"
    done = json.loads((out / "DONE-all.json").read_text())
    assert done == {"pass": True, "plan_sha256": plan_hash, "freeze_commit": FREEZE, "rows": len(study.completed), "not_selected": 0}


# ----------------------------------------------------------------------------- analysis

def test_audit_expects_grid_and_zero_only_and_refuses_not_selected_events(tmp_path):
    rows = [{**r, "cap": 4} for r in protocol.inventory()[:6]]
    plan, root = mini_plan(rows), tmp_path / "out"
    root.mkdir()
    ledger = EventLedger(root / "receipts.jsonl", "0" * 64, FREEZE, ["qualification-live"] + [r["id"] for r in rows])
    ledger.bind("dispatch:" + rows[0]["id"], {"kind": "dispatch", "row_id": rows[0]["id"]})
    report = analysis.audit(root, plan, partial=True)
    assert report["pass"] and report["unresolved_dispatch"] == [rows[0]["id"]] and report["not_selected"] == 0
    assert set(report["steps"]) == {"grid", "zero"} and report["steps"]["grid"]["planned"] == 6
    assert analysis.audit(root, plan, partial=True, plan_sha256="0" * 64, freeze=FREEZE)["pass"]
    for binding in ({"plan_sha256": "1" * 64}, {"freeze": "b" * 40}):
        with pytest.raises(ValueError):
            analysis.audit(root, plan, partial=True, **binding)
    with pytest.raises((ValueError, RuntimeError)):
        analysis.audit(root, plan, partial=False)
    (root / "selection.json").write_bytes(b"")
    assert analysis.audit(root, plan, partial=True)["selection_verified"] is False
    with pytest.raises(ValueError):
        analysis.audit(root, plan, partial=False)
    (root / "selection.json").unlink()
    # A plan with a conditional step, or a ledger with a not_selected event, is not this ladder.
    prompt = next(r for r in parent.inventory() if r["step"] == "prompt")
    with pytest.raises(ValueError):
        analysis.audit(root, mini_plan(rows + [prompt]), partial=True)
    root2 = tmp_path / "out2"
    root2.mkdir()
    ledger2 = EventLedger(root2 / "receipts.jsonl", "0" * 64, FREEZE, ["qualification-live"] + [r["id"] for r in rows])
    ledger2.bind("not_selected:" + rows[1]["id"], {"kind": "not_selected", "row_id": rows[1]["id"], "reason": "combo_not_matching"})
    with pytest.raises(ValueError):
        analysis.audit(root2, plan, partial=True)
    (root / "rows").mkdir()
    (root / "rows/bogus.json").write_text(json.dumps({"id": "bogus"}))
    with pytest.raises(ValueError):
        analysis.audit(root, plan, partial=True)


def test_analyze_writes_tables_summary_and_the_context_figure(tmp_path):
    reference = protocol.reference()
    one_repeat = lambda r: .31 if r["combo"] == "all|add|4" and r["feature_ids"] == [58667] and r["sign"] == -1 and r["seed"] == protocol.SEEDS[0] else 0.
    incoherent = lambda r: 3. if r["combo"] == "all|add|8" and r["feature_ids"] == [23893] and r["sign"] == 1 else 1.
    results = synthetic(grid_rows(), signature, one_repeat, incoherent) + synthetic(zero_rows(), lambda r: 0)
    table = protocol.step_one_table(results, reference, 1.)
    root = tmp_path / "out"
    write_rows(root, results)
    selection = analysis.selection(table, 1., "0" * 64)
    (root / "selection.json").write_text(protocol.canonical(selection) + "\n")
    context = context_csv(tmp_path / "context.csv", lambda f, s, k: {1: 0, 3: 0, 10: 1, 30: 2}[k] if s == -1 else 0)
    out = root / "analysis"
    summary = analysis.analyze(root, out, context=context)
    for ext in ("png", "pdf"):
        assert (out / f"{analysis.FIGURE}.{ext}").stat().st_size > 0
    assert sorted(p.name for p in out.glob("*.png")) == [analysis.FIGURE + ".png"], "one figure pair"
    assert json.loads((out / "selection.json").read_text()) == json.loads(protocol.canonical(selection))
    assert json.loads((out / "summary.json").read_text()) == json.loads(protocol.canonical(summary))
    assert summary["verdict"] == summary["verdict_if_valid"] == "coherent_match_found" and summary["delivery"]["valid"]
    assert summary["matched"] == ["all|add|5", "all|add|6"] and summary["rows"] == 105 and summary["zero_nll_median"] == 1.
    assert set(summary["combos"]) == set(protocol.COMBOS)
    assert summary["combos"]["all|add|4"]["flagged"] == 1 and summary["combos"]["all|add|8"]["coherent"] is False
    assert summary["combos"]["all|add|5"]["matches"] is True and "rank" not in summary["combos"]["all|add|5"]
    assert summary["rule_text"] == protocol.RULE_TEXT and summary["rules"] == protocol.RULES
    assert protocol.MAIN_RELEASE in summary["context"] and "context" in summary["context"]
    assert summary["delivery"]["arms"] == 21 and summary["delivery"]["trials_violating"] == 0
    classes = summary["position_classes"]["grid:all|add|5"]
    assert set(classes) == {"generated/regular"} and classes["generated/regular"]["positions"] == 40
    with (out / "rates.csv").open() as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == RATE_COLUMNS
        rates = list(reader)
    assert {r["step"] for r in rates} == {"grid", "zero"} and len(rates) == 21
    assert {(r["scope"], r["op"], r["system"], r["top_p"]) for r in rates} == {("all", "add", "none", "1.0")}
    cell = next(r for r in rates if r["combo"] == "all|add|5" and r["feature"] == "58667" and r["sign"] == "-1")
    assert (int(cell["n"]), int(cell["positive"]), int(cell["missing"]), float(cell["rate"]), int(cell["flagged"])) == (5, 5, 0, 1., 0)
    assert float(cell["wilson_low"]) == pytest.approx(.5655, abs=2e-3) and float(cell["wilson_high"]) == 1.
    flagged = next(r for r in rates if r["combo"] == "all|add|4" and r["feature"] == "58667" and r["sign"] == "-1")
    assert int(flagged["flagged"]) == 1 and float(flagged["rate"]) == 0.
    zero = next(r for r in rates if r["step"] == "zero")
    assert (int(zero["n"]), int(zero["positive"]), float(zero["rate"]), zero["sign"]) == (5, 0, 0., "0")
    with (out / "rates_paper.csv").open() as f:
        paper = list(csv.DictReader(f))
    assert len(paper) == 21 and sum(int(r["positive"]) for r in paper) == sum(int(r["positive"]) for r in rates)
    with (out / "combos.csv").open() as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == COMBO_COLUMNS
        combos = {r["combo"]: r for r in reader}
    assert list(combos) == list(protocol.COMBOS)
    assert float(combos["all|add|5"]["mad"]) == .1 and combos["all|add|5"]["matches"] == "True"
    assert float(combos["all|add|4"]["mad"]) == .5 and combos["all|add|4"]["coherent"] == "True" and combos["all|add|4"]["matches"] == "False"
    assert combos["all|add|8"]["coherent"] == "False"
    assert not any(v in ("None", "") for r in combos.values() for v in r.values()), "no constant-None column"
    with (out / "delivery.csv").open() as f:
        delivery = list(csv.DictReader(f))
    assert len(delivery) == 21 and all(r["violating"] == "0" and r["valid"] == "True" for r in delivery)
    # A stale rule text in selection.json is a disagreement with the frozen rule; a missing selection is recomputed.
    (root / "selection.json").write_text(protocol.canonical({**selection, "rule_text": parent.RULE_TEXT}) + "\n")
    with pytest.raises(ValueError):
        analysis.analyze(root, out, render=False)
    (root / "selection.json").unlink()
    recomputed = analysis.analyze(root, tmp_path / "again", render=False)
    assert recomputed["matched"] == summary["matched"]
    assert json.loads((tmp_path / "again/selection.json").read_text())["recomputed"] is True
    assert not list((tmp_path / "again").glob("*.png")), "render=False writes tables only"
    # The hash-bound main release parses as context with exactly the four main scales per fitted cell.
    real = analysis.context_cells()
    assert set(real) == {(f, s, k) for f in protocol.FEATURES for s in protocol.SIGNS for k in CONTEXT_SCALES}
    assert real[(58667, -1, 30)] == {"n": 5, "missing": 0, "flagged": 5, "rate": .4}
    assert real[(23893, -1, 10)]["rate"] == .2 and real[(23893, -1, 1)]["rate"] == 0.
    analysis.render(root, tmp_path / "again")
    assert (tmp_path / "again" / f"{analysis.FIGURE}.pdf").stat().st_size > 0


def test_context_cells_fail_closed_on_missing_overlapping_or_duplicated_scales(tmp_path):
    good = context_csv(tmp_path / "good.csv")
    cells = analysis.context_cells(good)
    assert set(cells) == {(f, s, k) for f in protocol.FEATURES for s in protocol.SIGNS for k in CONTEXT_SCALES}
    assert cells[(58667, -1, 30)] == {"n": 5, "missing": 0, "flagged": 3, "rate": 0.}
    overlap = dict(zip(RATE_COLUMNS, ["grid", "all|add|5", "all", "add", 5, 58667, -1, "none", 1.0, 5, 0, 0, 0., 0., 1., 0]))
    with pytest.raises(ValueError):
        analysis.context_cells(context_csv(tmp_path / "overlap.csv", extra=[overlap]))
    duplicate = dict(zip(RATE_COLUMNS, ["grid", "all|add|1", "all", "add", 1, 58667, -1, "none", 1.0, 5, 0, 0, 0., 0., 1., 0]))
    with pytest.raises(ValueError):
        analysis.context_cells(context_csv(tmp_path / "duplicate.csv", extra=[duplicate]))
    with (tmp_path / "good.csv").open() as f:
        rows = list(csv.DictReader(f))
    with (tmp_path / "missing.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RATE_COLUMNS)
        writer.writeheader()
        writer.writerows(r for r in rows if not (r["combo"] == "all|add|3" and r["feature"] == "23893"))
    with pytest.raises(ValueError):
        analysis.context_cells(tmp_path / "missing.csv")
    with (tmp_path / "columns.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[c for c in RATE_COLUMNS if c != "flagged"])
        writer.writeheader()
        writer.writerows({k: v for k, v in r.items() if k != "flagged"} for r in rows)
    with pytest.raises(ValueError):
        analysis.context_cells(tmp_path / "columns.csv")


def test_context_is_hash_bound_in_render_analyze_and_the_regeneration_cli(tmp_path, monkeypatch, capsys):
    results = synthetic(grid_rows(), signature) + synthetic(zero_rows(), lambda r: 0)
    root = tmp_path / "out"
    write_rows(root, results)
    context = context_csv(tmp_path / "context.csv")
    digest = protocol.sha(context)
    assert analysis.context_cells(context, digest) == analysis.context_cells(context)
    with pytest.raises(ValueError, match="Context release drifted"):
        analysis.context_cells(context, "0" * 64)
    with pytest.raises(ValueError, match="Context release drifted"):
        analysis.render(root, tmp_path / "fig", context, "0" * 64)
    assert not (tmp_path / "fig").exists() or not list((tmp_path / "fig").glob("*.png"))
    with pytest.raises(ValueError, match="Context release drifted"):
        analysis.analyze(root, tmp_path / "a", context=context, context_sha256="0" * 64)
    assert not list((tmp_path / "a").glob("*.png")), "tables may exist; no figure is drawn from unbound context"
    # The drift check precedes the plotting import, so a missing matplotlib cannot mask a drifted context.
    import builtins
    real_import = builtins.__import__

    def no_matplotlib(name, *args, **kwargs):
        if name.startswith("matplotlib"):
            raise ImportError("No module named 'matplotlib'", name="matplotlib")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_matplotlib)
    with pytest.raises(ValueError, match="Context release drifted"):
        analysis.render(root, tmp_path / "fig2", context, "0" * 64)
    with pytest.raises(ImportError):
        analysis.render(root, tmp_path / "fig2", context, digest)
    monkeypatch.setattr(builtins, "__import__", real_import)
    # The CLI loads the plan and binds the context to its input hash; a stale or edited context is refused.
    plan_path = tmp_path / "PLAN.json"
    plan_path.write_text("{}")
    loaded = []
    monkeypatch.setattr(protocol, "load_plan", lambda path, freeze=None: (loaded.append(str(path)),
                        {"input_hashes": {protocol.REFERENCE_CSV: "0" * 64, protocol.MAIN_RELEASE: digest}})[1])
    analysis.main(["--root", str(root), "--out", str(tmp_path / "cli"), "--plan", str(plan_path), "--context", str(context)])
    assert loaded == [str(plan_path)] and (tmp_path / "cli" / f"{analysis.FIGURE}.png").stat().st_size > 0
    assert json.loads(capsys.readouterr().out)["rows"] == 105
    analysis.main(["--root", str(root), "--out", str(tmp_path / "cli-default"), "--context", str(context)])
    assert loaded[-1] == str(protocol.ROOT / protocol.PLAN_PATH), "the default plan is the frozen fine plan"
    with (tmp_path / "context.csv").open("a") as f:
        f.write("\n")
    with pytest.raises(ValueError, match="Context release drifted"):
        analysis.main(["--root", str(root), "--out", str(tmp_path / "cli2"), "--plan", str(plan_path), "--context", str(context)])
    assert not list((tmp_path / "cli2").glob("*.png"))


def test_delivery_violations_invalidate_an_arm_and_the_verdict(tmp_path):
    bad = lambda r: r["combo"] == "all|add|5" and r["feature_ids"] == [58667] and r["sign"] == -1 and r["seed"] == protocol.SEEDS[0]
    results = synthetic(grid_rows(), signature, cosine=lambda r: .9 if bad(r) else 1.) + synthetic(zero_rows(), lambda r: 0)
    root = tmp_path / "out"
    write_rows(root, results)
    summary = analysis.analyze(root, root / "analysis", render=False)
    assert summary["verdict"] == "invalid" and summary["verdict_if_valid"] == "coherent_match_found"
    assert summary["delivery"]["valid"] is False and summary["delivery"]["trials_violating"] == 1
    assert summary["delivery"]["invalid_arms"] == [{"step": "grid", "combo": "all|add|5", "scope": "all", "op": "add",
                                                    "scale": 5, "feature": 58667, "sign": -1, "system": "none", "top_p": 1.}]
    with (root / "analysis/delivery.csv").open() as f:
        arm = next(r for r in csv.DictReader(f) if r["combo"] == "all|add|5" and r["feature"] == "58667" and r["sign"] == "-1")
    assert (arm["n"], arm["violating"], arm["valid"]) == ("5", "1", "False") and float(arm["share"]) == .2
    assert analysis.delivery_violation is parent_analysis.delivery_violation
    assert not list((root / "analysis").glob("*.png"))
    assert json.loads((root / "analysis/selection.json").read_text())["recomputed"] is True


# ----------------------------------------------------------------------------- controller

def test_controller_namespace_constants_and_budget_import():
    assert controller.PREFIX == "claude-opmatch-fine-20261003-" and controller.NAMESPACE == "operator-matching-fine-controller"
    assert controller.OWNED_OUT == controller.ROOT / "out/operator-matching-fine-20261003" and controller.ROOT == protocol.ROOT
    assert controller.ATTEMPTS == ("main", "main-2")
    assert controller.protocol is protocol and controller.analysis is analysis
    assert controller.TOTAL_USD == Decimal("100")
    source = Path(controller.__file__).read_text()
    assert not re.search(r'"(?:15|35|40|60|100|200)"', source), "budget figures must come from protocol, not literals"
    assert "> 200" not in source and "<= 200" not in source and "experiments.operator_matching.runner" not in source
    assert "experiments.operator_matching.protocol" not in source and "claude-opmatch-20261002" not in source
    # Faithful fork: only the namespaced lines differ from the parent controller.
    parent_source = (Path(parent.__file__).parent / "controller.py").read_text()
    differing = [l for l in parent_source.splitlines() if l.strip() and l not in source.splitlines()]
    assert all(any(token in l for token in ("opmatch", "operator-matching", "operator_matching", "$60", "cheap test pod",
                                             "Reuse the audited", "markers. New namespace", "budget contract is imported",
                                             "replacement main pod"))
               for l in differing), differing
    # The docstring states the enforced arithmetic rather than the parent's $60 replacement promise.
    doc = controller.__doc__
    assert "$13.78" in doc and "$1.22" in doc and "Entire timer is not funded" in doc


def test_worker_script_binds_fine_module_tests_and_plan_prefix():
    relative = "data/operator_matching/fine_plan_20261003/PLAN.json"
    for kind in ("cheap", "main"):
        script = controller.worker_script(kind, relative, FREEZE, "2026-10-03T12:00:00+00:00")
        assert subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True).returncode == 0
        assert "git checkout --detach " + FREEZE in script and relative in script
        assert "git sparse-checkout init --cone" in script and "git sparse-checkout set " in script
        assert all(path in script for path in protocol.CHECKOUT_PATHS)
        assert "experiments.operator_matching_fine.protocol import load_plan" in script
        assert "experiments.operator_matching.protocol import load_plan" not in script
        assert "pip install -r " + protocol.REQUIREMENTS in script
        assert "RUNPOD_API_KEY" not in script and "OPENAI_API_KEY" not in script and "berg_ensemble" not in script
    cheap = controller.worker_script("cheap", relative, FREEZE, "2026-10-03T12:00:00+00:00")
    pytest_line = next(l for l in cheap.splitlines() if "-m pytest" in l)
    assert "tests/test_operator_matching.py tests/test_operator_matching_fine.py -q" in pytest_line, \
        "the parent's CUDA exact-path tests are re-run under this freeze before the ladder's"
    assert "BERG_TEST_DEVICE=cuda" in cheap
    main = controller.worker_script("main", relative, FREEZE, "2026-10-03T12:00:00+00:00")
    assert "experiments.operator_matching_fine.runner" in main and "experiments.operator_matching.runner" not in main
    assert "--deadline-utc" in main
    assert (protocol.ROOT / protocol.REQUIREMENTS).read_text().count("matplotlib==") == 1
    for bad in ("../bad", "/abs/" + relative, "data/operator_matching/plan_20261002/PLAN.json",
                "data/operator_matching/fine_plan_20261003/../x.json", "data/berg_ensemble_replication/plan_20261001/PLAN.json"):
        with pytest.raises(ValueError):
            controller.worker_script("main", bad, FREEZE, "bad")
    with pytest.raises(ValueError):
        controller.worker_script("main", relative, "a" * 39, "bad")
    with pytest.raises(ValueError):
        controller.worker_script("medium", relative, FREEZE, "bad")


@pytest.fixture
def ctrl(tmp_path, monkeypatch):
    now = datetime(2026, 10, 3, tzinfo=timezone.utc)
    monkeypatch.setattr(controller, "ROOT", tmp_path)
    monkeypatch.setattr(controller, "OWNED_OUT", tmp_path / "out")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"budget": protocol.BUDGET}))
    monkeypatch.setattr(protocol, "load_plan", lambda *_: {"budget": deepcopy(protocol.BUDGET)})
    key = tmp_path / "key"
    key.write_text("test-only")
    Path(str(key) + ".pub").write_text(PUBLIC_KEY)
    monkeypatch.setattr(controller.base, "KEY", key)
    monkeypatch.setattr(controller.base, "verify_public", lambda *_: None)
    monkeypatch.setenv("HF_TOKEN", "hf_dummy_test_only")
    api = FakeAPI(lambda: now)

    def make(kind="main", out=None, receipt=".1"):
        c = controller.Controller(plan, FREEZE, out or tmp_path / "out", kind, api, clock=lambda: now,
                                  monotonic=lambda: 0, sleep=Mock(), run=Mock())
        c.disk_check, c.start_worker = Mock(), Mock()
        c.cheap_receipt = Mock(return_value=Decimal(receipt))
        return c
    return make, api


def test_controller_never_adopts_and_enforces_prefix_and_binding(ctrl):
    make, api = ctrl
    api.extra = [{"id": "stray", "name": controller.PREFIX + "main-" + "0" * 12, "createdAt": "2026-10-02T00:00:00+00:00"},
                 {"id": "parent", "name": "claude-opmatch-20261002-main-" + "1" * 12, "createdAt": "2026-10-02T00:00:00+00:00"}]
    c = make()
    assert c.base == c.out / controller.NAMESPACE / "main" and c.hard_seconds == protocol.MAIN_SECONDS == 7200
    assert make("cheap").hard_seconds == protocol.CHEAP_SECONDS
    with pytest.raises(ValueError):
        c.owned()
    pod = c.launch()
    assert pod["id"] == "newowned1" and re.fullmatch(re.escape(controller.PREFIX) + "main-[0-9a-f]{12}", pod["name"])
    intent = c.event("create-intent")["data"]
    assert intent["prior_total_usd"] == protocol.PRIOR_USD == "18.790675" and intent["prior_new_usd"] == "0.1"
    assert {"stray", "parent", controller.base.BLOCKED} <= set(intent["blocked"])
    assert intent["plan_sha256"] == c.plan_hash and intent["freeze_commit"] == FREEZE
    assert intent["hard_deadline_utc"] == "2026-10-03T02:00:00+00:00" and intent["deadline_utc"] == "2026-10-03T01:50:00+00:00"
    with pytest.raises(ValueError):
        c.launch()
    assert c._new_pod(pod, intent)
    assert not c._new_pod(dict(pod, id="stray"), intent)
    assert not c._new_pod(dict(pod, name="claude-opmatch-20261002-main-" + pod["name"][-12:]), intent)
    assert not c._new_pod(pod, {**intent, "payload": {**intent["payload"], "name": "claude-opmatch-20261002-main-" + pod["name"][-12:]}})
    assert not c._new_pod(pod, {**intent, "plan_sha256": "0" * 64})
    assert not c._new_pod(pod, {**intent, "freeze_commit": "b" * 40})
    foreign = dict(pod, id="foreign")
    with pytest.raises(ValueError):
        c._ssh(foreign, "true")
    with pytest.raises(ValueError):
        c.cost_check(foreign)
    assert c.cost_check(api.pod) == 0
    with pytest.raises(ValueError):
        c.cost_check(dict(api.pod, cost=99))
    with pytest.raises(ValueError):
        c.cost_check(api.pod, horizon=protocol.MAIN_SECONDS)
    with pytest.raises(ValueError):
        make(out=c.out.parent / "elsewhere")
    config = c.event("controller:config")["data"]
    assert config["namespace"] == controller.NAMESPACE and config["budget"] == protocol.BUDGET and config["hard_seconds"] == 7200


def test_budget_contract_mismatch_and_caps_are_enforced(ctrl, monkeypatch):
    make, api = ctrl
    for change in ({"new_cap_usd": "16"}, {"new_cap_usd": "60"}, {"total_usd": "200"}, {"prior_usd": "0.278924"}, {"main_seconds": 21600}):
        monkeypatch.setattr(protocol, "load_plan", lambda *_, c=change: {"budget": {**protocol.BUDGET, **c}})
        with pytest.raises(ValueError):
            make()
    monkeypatch.setattr(protocol, "load_plan", lambda *_: {"budget": deepcopy(protocol.BUDGET)})
    # B200 at the quoted ceiling for the full two-hour timer costs (6.79 + 0.10) * 2 = 13.78 of the $15 cap.
    with pytest.raises(ValueError):
        make(receipt="1.3").launch()
    c = make(receipt="1.2")
    c.launch()
    assert c.event("create-intent")["data"]["prior_new_usd"] == "1.2"
    assert c.cost_check(api.pod) == 0
    accounting = [e["data"] for e in c.ledger.read() if e["id"].startswith("accounting:")][-1]
    assert Decimal(accounting["cumulative_projected_usd"]) < Decimal(protocol.BUDGET["total_usd"])
    assert Decimal(accounting["cumulative_projected_usd"]) > Decimal(protocol.PRIOR_USD) + Decimal("1.2")
    # The $100 total binds through the protocol prior, never a literal: push prior spending to the edge.
    for prior, ok in (("85", True), ("99", False)):
        monkeypatch.setattr(protocol, "PRIOR_USD", prior)
        c.budget["prior_usd"] = prior
        if ok:
            c.cost_check(api.pod)
        else:
            with pytest.raises(ValueError):
                c.cost_check(api.pod)


def test_dry_run_main_makes_no_network_calls(tmp_path, monkeypatch, capsys):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"budget": protocol.BUDGET}))
    monkeypatch.setattr(protocol, "load_plan", lambda *_: {"budget": deepcopy(protocol.BUDGET)})
    api = Mock(side_effect=AssertionError("network client constructed during a dry run"))
    monkeypatch.setattr(controller.base, "RunPodV2", api)
    monkeypatch.setattr(controller, "Controller", Mock(side_effect=AssertionError("controller built during a dry run")))
    monkeypatch.setattr(sys, "argv", ["controller", "--plan", str(plan), "--freeze", FREEZE, "--kind", "main"])
    controller.main()
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert printed.items() >= {"dry_run": True, "network_calls": 0, "new_cap_usd": "15", "total_usd": "100"}.items()
    assert not api.called and not controller.Controller.called
