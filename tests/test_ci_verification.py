"""CI setup is mocked; no apt, pip installation or network fetch in tests."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from scripts import prepare_ci_verification as ci

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/verify.yml"
WORKFLOW_SHA = "ed6b45ba86fc0f3c315dc1ac45e297cb7a67757596206efaf6f720624667c4be"


def forbidden(*args, **kwargs):
    pytest.fail("Unexpected external operation")


@pytest.mark.parametrize("mode", ["tests", "paper"])
@pytest.mark.parametrize("value", [None, "false", "TRUE"])
def test_local_checks_never_fetch_or_install(mode, value):
    result = ci.prepare(mode, environ={"GITHUB_ACTIONS": value}, run=forbidden, which=forbidden)
    assert result == {"prepared": False, "reason": "not_github_actions"}


class Environment:
    def __init__(self, *, shallow=True, poppler=False, fail=None, ineffective=False):
        self.shallow, self.poppler, self.fail, self.ineffective = shallow, poppler, fail, ineffective
        self.calls = []

    def which(self, tool):
        return "/usr/bin/" + tool if self.poppler else None

    def run(self, args, **kwargs):
        self.calls.append((args, kwargs))
        assert 0 < kwargs["timeout"] <= 300
        if self.fail and self.fail in args:
            raise subprocess.CalledProcessError(1, args)
        if args == ["git", "rev-parse", "--is-shallow-repository"]:
            return "true" if self.shallow else "false"
        if args == ["git", "rev-parse", "--verify", "HEAD"]:
            return "a" * 40
        if args[:2] == ["git", "fetch"] and not self.ineffective:
            self.shallow = False
        if "poppler-utils" in args and not self.ineffective:
            self.poppler = True

    def prepare(self, mode):
        return ci.prepare(mode, environ={"GITHUB_ACTIONS": "true"}, platform="linux",
                          run=self.run, which=self.which, python="selected-python")


def test_tests_job_only_adds_poppler():
    env = Environment()
    result = env.prepare("tests")
    assert [args for args, _ in env.calls] == [
        ["sudo", "apt-get", "update"],
        ["sudo", "apt-get", "install", "--yes", "--no-install-recommends", "poppler-utils"]]
    assert result["prepared"] and result["python_dependencies"] == "existing_workflow_install"


@pytest.mark.parametrize("shallow", [True, False])
def test_paper_job_has_full_history_cpu_dependencies_and_poppler(shallow):
    env = Environment(shallow=shallow)
    result = env.prepare("paper")
    commands = [args for args, _ in env.calls]
    assert sum(args[:2] == ["git", "fetch"] for args in commands) == int(shallow)
    if shallow:
        fetch = next(args for args in commands if args[:2] == ["git", "fetch"])
        assert fetch[-2:] == ["+refs/heads/*:refs/remotes/origin/*", "a" * 40]
        assert "--tags" in fetch
    assert not env.shallow and env.poppler
    assert commands[-2:] == [
        ["selected-python", "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements-ci.txt"],
        ["selected-python", "-m", "pip", "check"]]
    assert result["git_history"] == "full"
    assert not any("checkout" in args or "reset" in args or "model" in args for args in commands)


def test_existing_poppler_does_not_need_sudo():
    env = Environment(poppler=True)
    env.prepare("tests")
    assert env.calls == []


@pytest.mark.parametrize("failure", ["fetch", "update", "poppler-utils", "pip"])
def test_setup_failure_is_not_ignored_or_retried(failure):
    env = Environment(fail=failure)
    with pytest.raises(subprocess.CalledProcessError):
        env.prepare("paper")
    assert sum(failure in args for args, _ in env.calls) == 1
    assert failure in env.calls[-1][0]


@pytest.mark.parametrize("shallow", [True, False])
def test_successful_exit_without_required_state_still_fails(shallow):
    env = Environment(shallow=shallow, ineffective=True)
    with pytest.raises(ValueError, match="shallow boundary|Poppler"):
        env.prepare("paper")
    assert not any("pip" in args for args, _ in env.calls)


def test_unexpected_platform_or_depth_is_rejected():
    with pytest.raises(ValueError, match="Ubuntu/Linux"):
        ci.prepare("paper", environ={"GITHUB_ACTIONS": "true"}, platform="darwin", run=forbidden)
    with pytest.raises(ValueError, match="checkout depth"):
        ci.prepare("paper", environ={"GITHUB_ACTIONS": "true"}, platform="linux",
                   run=lambda *args, **kwargs: "unknown")


@pytest.mark.parametrize("head", ["unknown", "b" * 40])
def test_invalid_or_changed_detached_head_is_rejected(head):
    env = Environment()
    original = env.run
    reads = []
    def run(args, **kwargs):
        result = original(args, **kwargs)
        if args == ["git", "rev-parse", "--verify", "HEAD"]:
            reads.append(result)
            if head == "unknown" or len(reads) > 1:
                return head
        return result
    with pytest.raises(ValueError, match="checked-out commit"):
        ci.prepare("paper", environ={"GITHUB_ACTIONS": "true"}, platform="linux", run=run, which=env.which)


def test_frozen_workflow_and_frontier_plan_bindings_stay_exact():
    assert hashlib.sha256((ROOT / WORKFLOW).read_bytes()).hexdigest() == WORKFLOW_SHA
    for name in ("plan_20261002", "completed_20261002"):
        plan = json.loads((ROOT / "data/frontier_bilingual_b1" / name / "PLAN.json").read_bytes())
        assert plan["sources"][WORKFLOW] == WORKFLOW_SHA
        assert not {"Makefile", "scripts/prepare_ci_verification.py", "tests/test_ci_verification.py"} & plan["sources"].keys()
    workflow = (ROOT / WORKFLOW).read_text()
    tests_job = workflow.split("  paper-evidence:", 1)[0]
    assert "fetch-depth: 0" in tests_job
    assert "-r requirements-ci.txt" in tests_job and "-r requirements-ci-torch.txt" in tests_job


@pytest.mark.parametrize("actions", ["true", "false"])
def test_make_preparation_precedes_unchanged_verifiers_only_in_ci(actions):
    output = subprocess.check_output(
        ["make", "--no-print-directory", "-n", "test", "paper-verify", "PYTHON=python", "GITHUB_ACTIONS=" + actions],
        cwd=ROOT, text=True, env={k: v for k, v in os.environ.items() if k not in {"MAKEFLAGS", "MFLAGS"}})
    assert "python -m pytest tests" in output and "python scripts/verify_evidence.py" in output
    if actions == "true":
        assert output.index("prepare_ci_verification.py tests") < output.index("python -m pytest tests")
        assert output.index("prepare_ci_verification.py paper") < output.index("python scripts/verify_evidence.py")
    else:
        assert "prepare_ci_verification.py" not in output
