"""Post-outcome filesystem checks, outside the frozen experiment source glob."""
import os
from pathlib import Path

import pytest

from scripts import reproduce_bilingual_b1 as r


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path.resolve()
    raw, judges, plan, out = (root / n for n in ("raw", "judges", "plan.json", "derived"))
    raw.mkdir()
    judges.mkdir()
    (raw / "response.json").write_text("{}\n")
    (judges / "receipts.jsonl").write_text("{}\n")
    plan.write_text("{}\n")
    return raw, judges, plan, out


def test_regular_inputs_preserve_frozen_call_and_result(inputs, monkeypatch):
    raw, judges, plan, out = inputs
    calls = []
    def frozen(*args):
        calls.append(args)
        return {"pass": True, "outputs": 3}
    monkeypatch.setattr(r.release, "reproduce", frozen)
    result = r.reproduce(raw, judges, plan, "a" * 40, out)
    assert calls == [(raw, judges, plan, "a" * 40, out)]
    assert result == {"pass": True, "outputs": 3, "input_tree_preflight": {
        "pass": True, "raw_files": 1, "judge_files": 1}}


@pytest.mark.parametrize("kind", ["file", "directory", "root", "ancestor", "plan", "output"])
def test_symlinks_fail_before_copy_or_analysis(inputs, monkeypatch, kind):
    raw, judges, plan, out = inputs
    alias = raw.parent / "alias"
    if kind == "file":
        (raw / "linked.json").symlink_to(plan)
    elif kind == "directory":
        (raw / "linked").symlink_to(judges, target_is_directory=True)
    elif kind == "root":
        alias.symlink_to(raw, target_is_directory=True)
        raw = alias
    elif kind == "ancestor":
        alias.symlink_to(raw.parent, target_is_directory=True)
        raw = alias / raw.name
    elif kind == "plan":
        alias.symlink_to(plan)
        plan = alias
    else:
        alias.symlink_to(raw.parent, target_is_directory=True)
        out = alias / "derived"
    monkeypatch.setattr(r.release, "reproduce", lambda *_: pytest.fail("Frozen code called"))
    with pytest.raises(ValueError):
        r.reproduce(raw, judges, plan, "a" * 40, out)


def test_fifo_fails_without_opening(inputs, monkeypatch):
    raw, judges, plan, out = inputs
    os.mkfifo(raw / "pipe")
    monkeypatch.setattr(r.release, "reproduce", lambda *_: pytest.fail("Frozen code called"))
    with pytest.raises(ValueError, match="Nonregular"):
        r.reproduce(raw, judges, plan, "a" * 40, out)


def test_post_copy_symlink_is_not_accepted(inputs, monkeypatch):
    raw, judges, plan, out = inputs
    def frozen(*_):
        (raw / "late-link").symlink_to(plan)
        return {"pass": True}
    monkeypatch.setattr(r.release, "reproduce", frozen)
    with pytest.raises(ValueError):
        r.reproduce(raw, judges, plan, "a" * 40, out)


def test_new_input_file_is_not_accepted(inputs, monkeypatch):
    raw, judges, plan, out = inputs
    def frozen(*_):
        (judges / "late.json").write_text("{}\n")
        return {"pass": True}
    monkeypatch.setattr(r.release, "reproduce", frozen)
    with pytest.raises(ValueError, match="inventory changed"):
        r.reproduce(raw, judges, plan, "a" * 40, out)
