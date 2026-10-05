"""Offline controller contract tests: provider, SSH and model work are mocked."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from experiments import berg_dose_exposure as package
from experiments.berg_dose_exposure import controller as c

FREEZE = "a" * 40
UTC = datetime(2026, 10, 4, tzinfo=timezone.utc)
RELATIVE = "data/berg_dose_exposure/plan_20261004/PLAN.json"
PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest test-only"
CUDA_XML = ('<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0">'
            '<testcase classname="tests.test_dose_exposure_backend" name="test_cuda"/>'
            '<testcase classname="tests.test_dose_exposure_runner" name="test_runner"/>'
            '</testsuite></testsuites>')


def stub_plan():
    return {"budget": deepcopy(c.BUDGET),
            "source_hashes": dict.fromkeys(c.SPARSE_REQUIRED_SOURCES, "b" * 64),
            "input_hashes": {"data/berg_dose_exposure/plan_20261004/POWER.json": "c" * 64}}


class FakeAPI:
    writable = True

    def __init__(self, rig):
        self.rig = rig
        self.calls, self.extra = [], [{"id": "foreign1", "name": "unrelated"}]
        self.pod, self.deleted = None, False
        self.lost_response = self.missing = self.delete_stays = self.inventory_stays = False
        self.kind = "cheap"

    def inventory(self):
        self.calls.append(("GET", "/pods", None))
        return deepcopy(self.extra + ([self.pod] if self.pod and (not self.deleted or self.inventory_stays) else []))

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        gpu, rate, memory = c.base.HARDWARE[self.kind]
        if path.startswith("/catalog/"):
            return 200, {"id": gpu, "memory": memory, "secure": True,
                         "price": {"secure": str(rate)}, "availability": "HIGH"}
        if method == "POST":
            self.pod = {**deepcopy(body), "id": "owned1", "createdAt": self.rig.now.isoformat(),
                        "cost": str(rate), "status": "RUNNING", "gpu": {"id": gpu, "count": 1, "memory": memory},
                        "ssh": {"direct": {"host": "192.0.2.1", "port": 12345, "username": "root"}}}
            if self.missing:
                self.pod = None
            if self.lost_response or self.missing:
                raise RuntimeError("Uncertain POST")
            return 201, deepcopy(self.pod)
        assert path == "/pods/owned1", "Foreign pod operation"
        if method == "DELETE":
            self.deleted = not self.delete_stays
            return 204, None
        if self.deleted:
            raise c.base.ApiError(404)
        return 200, deepcopy(self.pod)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    class Rig:
        def __init__(self):
            self.root = tmp_path.resolve()
            self.out = self.root / "out/dose-exposure-20261004"
            self.plan = self.root / RELATIVE
            self.plan.parent.mkdir(parents=True)
            self.plan_data = stub_plan()
            self.plan.write_text(json.dumps(self.plan_data))
            self.now, self.ticks = UTC, 0
            self.api = FakeAPI(self)
            self.public = Mock()

        def advance(self, seconds):
            self.ticks += seconds
            self.now += timedelta(seconds=seconds)

        def controller(self, kind="cheap", **kwargs):
            self.api.kind = kind
            ctrl = c.Controller(self.plan, FREEZE, self.out, kind, self.api,
                                clock=lambda: self.now, monotonic=lambda: self.ticks,
                                sleep=self.advance, run=Mock(side_effect=AssertionError("Unexpected subprocess")), **kwargs)
            ctrl.disk_check = Mock()
            return ctrl

        def launch(self, ctrl):
            with patch.object(ctrl, "start_worker"):
                ctrl.launch()
            return ctrl

        def main(self, prior="0.42"):
            ctrl = self.controller("main")
            ctrl.cheap_receipt = Mock(return_value=Decimal(prior))
            return ctrl

        def snapshot(self, ctrl, *, corrupt=False, fail=False, files=None):
            files = dict(files or {"rows/first.json": b'{"id":"first"}'})
            ctrl.ledger.bind("worker-intent", {"worker_id": "b" * 32, "pod_id": "owned1",
                "plan_sha256": ctrl.plan_hash, "freeze_commit": FREEZE})
            actions = []

            def signal(pod, action):
                actions.append(action)
                if action == "stop":
                    files["controller-stopped.json"] = b'{"stopped":true}'
                return {"action": action, "verified": True}

            def run(argv, **kwargs):
                assert argv[0] == "rsync"
                for name, raw in files.items():
                    path = Path(argv[-1]) / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw + (b"corrupt" if corrupt else b""))
                return subprocess.CompletedProcess(argv, int(fail), b"", b"")

            ctrl.signal_worker = Mock(side_effect=signal)
            ctrl._ssh = Mock(side_effect=lambda *a, **kw: json.dumps(
                {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}).encode())
            ctrl.run = Mock(side_effect=run)
            return actions

        def qualified_cheap(self):
            ctrl = self.launch(self.controller())
            self.snapshot(ctrl, files={"DONE-all.json": b'{"pass":true,"scope":"tiny_cuda_exact_path"}',
                "controller-exit.json": b'{"exit_code":0}', "tests.xml": CUDA_XML.encode()})
            self.advance(100)
            ctrl.terminate()
            return ctrl

    result = Rig()
    monkeypatch.setattr(c, "ROOT", result.root)
    monkeypatch.setattr(c, "OWNED_OUT", result.out)
    monkeypatch.setattr(package, "protocol", SimpleNamespace(BUDGET=deepcopy(c.BUDGET),
        load_plan=Mock(side_effect=lambda *_: deepcopy(result.plan_data))), raising=False)
    key = result.root / "key"
    key.write_text("test-only")
    Path(str(key) + ".pub").write_text(PUBLIC_KEY)
    monkeypatch.setattr(c.base, "KEY", key)
    monkeypatch.setattr(c.base, "verify_public", result.public)
    monkeypatch.setenv("HF_TOKEN", "hf_dummy_test_only")
    monkeypatch.setenv("RUNPOD_API_KEY", "rp_dummy_test_only")
    monkeypatch.setenv("OPENAI_API_KEY", "api_dummy_test_only")
    monkeypatch.setattr("urllib.request.OpenerDirector.open", Mock(side_effect=AssertionError("Network forbidden")))
    return result


def test_separate_budget_contract():
    assert c.PRIOR_USD == "8.837266296602623" and c.TOTAL == "50"
    assert Decimal(c.PRIOR_USD) + Decimal(c.NEW_CAP_USD) < Decimal(c.TOTAL)
    assert (c.MAIN_SECONDS, c.CHEAP_SECONDS, c.RESERVE_SECONDS) == (19800, 1800, 600)
    assert c.BUDGET["new_pro_calls"] == c.BUDGET["external_judge_calls"] == 0


@pytest.mark.parametrize("key,value", [("prior_usd", "72.50"), ("new_cap_usd", "35"),
    ("total_usd", "200"), ("main_seconds", 16200), ("reserve_seconds", 0),
    ("cheap_seconds", 1800.0), ("new_pro_calls", False), ("external_judge_calls", 1)])
def test_budget_drift_rejected_before_state(rig, key, value):
    rig.plan_data["budget"][key] = value
    with pytest.raises(ValueError, match="budget"):
        rig.controller()
    assert not rig.out.exists() and not rig.api.calls


def test_protocol_budget_cannot_expand_authorization(rig):
    package.protocol.BUDGET["total_usd"] = "51"
    with pytest.raises(ValueError, match="budget"):
        rig.controller()


def test_canonical_root_uses_shared_git_directory(tmp_path):
    common = tmp_path / "primary/.git"
    with patch.object(c.subprocess, "check_output", return_value=str(common) + "\n") as read:
        assert c.canonical_root(tmp_path / "worktree") == common.parent
    assert "--git-common-dir" in read.call_args.args[0]
    assert read.call_args.kwargs["cwd"] == tmp_path / "worktree"


def test_operational_root_is_main_checkout():
    assert c.OWNED_OUT == c.OPERATIONAL_ROOT / "out/dose-exposure-20261004"
    assert c.OPERATIONAL_ROOT == c.canonical_root()


def test_alternative_root_and_symlinks_rejected(rig):
    with pytest.raises(ValueError, match="canonical"):
        c.Controller(rig.plan, FREEZE, rig.root / "different", "cheap", rig.api)
    rig.out.mkdir(parents=True)
    (rig.out / c.NAMESPACE).symlink_to(rig.root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        rig.controller()


def test_public_freeze_before_create_and_block_all_inventory(rig):
    rig.api.extra += [{"id": "foreign2", "name": c.PREFIX + "main-012345abcdef"}]
    rig.public.side_effect = lambda *args: pytest.fail("Paid dispatch preceded public freeze") if any(
        m == "POST" for m, _, _ in rig.api.calls) else None
    ctrl = rig.launch(rig.controller())
    intent = ctrl.event("create-intent")["data"]
    assert set(intent["blocked"]) == {"foreign1", "foreign2", c.base.BLOCKED}
    assert intent["prior_total_usd"] == c.PRIOR_USD
    assert ctrl.owned()["name"].startswith(c.PREFIX + "cheap-")
    rig.public.assert_called_once_with(ctrl.plan_hash, RELATIVE, FREEZE)
    assert intent["payload"]["env"] == {"PUBLIC_KEY": PUBLIC_KEY}


def test_supplied_unrelated_pods_are_blocked_and_untouched(rig):
    ids = {"xlll4ou2jfony0", "un72kuat0b3w8c", "i5xq2o025exq8c"}
    rig.api.extra = [{"id": pod_id, "name": "unrelated"} for pod_id in sorted(ids)]
    ctrl = rig.launch(rig.controller())
    intent = ctrl.event("create-intent")["data"]
    assert ids <= set(intent["blocked"])
    for pod_id in ids:
        foreign = {**ctrl.owned(), "id": pod_id}
        assert not ctrl._new_pod(foreign, intent)
        with pytest.raises(ValueError):
            ctrl._register(foreign)
    assert ctrl.terminate()["data"]["inventory_ids"] == sorted(ids)
    assert not any(path == "/pods/" + pod_id for _, path, _ in rig.api.calls for pod_id in ids)


def test_quoted_full_lifetimes_fit_fifty_including_storage(rig):
    rig.api.kind = "cheap"
    cheap = c.base.quote(rig.api, "cheap")
    rig.api.kind = "main"
    main = c.base.quote(rig.api, "main")
    assert cheap == {"hourly_rate_usd": "0.74", "storage_hourly_usd": "0.10"}
    assert main == {"hourly_rate_usd": "6.79", "storage_hourly_usd": "0.10"}
    maximum = sum((c._number(quote["hourly_rate_usd"]) + c._number(quote["storage_hourly_usd"]))
                  * seconds / 3600 for quote, seconds in ((cheap, c.CHEAP_SECONDS), (main, c.MAIN_SECONDS)))
    assert maximum == Decimal("38.315") < Decimal(c.NEW_CAP_USD)
    assert Decimal(c.PRIOR_USD) + maximum == Decimal("47.152266296602623") < Decimal(c.TOTAL)
    assert all(method == "GET" for method, _, _ in rig.api.calls)


def test_freeze_failure_and_plan_change_prevent_create(rig):
    ctrl = rig.controller()
    rig.public.side_effect = ValueError("Public freeze missing")
    with pytest.raises(ValueError, match="freeze"):
        ctrl.launch()
    assert not rig.api.calls
    rig.plan.write_text("changed")
    with pytest.raises(ValueError, match="Plan changed"):
        ctrl.launch()
    assert not rig.api.calls


@pytest.mark.parametrize("kind", ["cheap", "main"])
def test_no_second_launch_even_after_restart_or_closure(rig, kind):
    ctrl = rig.main() if kind == "main" else rig.controller()
    rig.launch(ctrl)
    ctrl.terminate()
    for candidate in (ctrl, rig.controller(kind)):
        with pytest.raises(ValueError, match="Fresh explicit"):
            candidate.launch()
    assert sum(m == "POST" for m, _, _ in rig.api.calls) == 1


def test_ambiguous_create_reconciles_without_replacement(rig):
    rig.api.lost_response = True
    ctrl = rig.launch(rig.controller())
    assert ctrl.owned()["id"] == "owned1"
    assert any(e["id"].startswith("create-reconciled:") for e in ctrl.ledger.read())
    assert sum(m == "POST" for m, _, _ in rig.api.calls) == 1


def test_unresolved_create_retains_intent_and_blocks_second_post(rig):
    rig.api.missing = True
    ctrl = rig.controller()
    with pytest.raises(RuntimeError, match="unresolved"):
        ctrl.launch()
    assert ctrl.event("create-intent") and not ctrl.event("created")
    with pytest.raises(ValueError, match="Fresh explicit"):
        rig.controller().launch()
    assert sum(m == "POST" for m, _, _ in rig.api.calls) == 1


def test_foreign_pods_never_adopted_or_signalled(rig):
    ctrl = rig.launch(rig.controller())
    foreign = {**ctrl.owned(), "id": "foreign1"}
    assert not ctrl._new_pod(foreign, ctrl.event("create-intent")["data"])
    for operation in (ctrl.cost_check, ctrl._register, ctrl._confirm_closed):
        with pytest.raises(ValueError):
            operation(foreign)
    with pytest.raises(ValueError):
        ctrl._ssh(foreign, "true")
    with pytest.raises(ValueError):
        ctrl.signal_worker(foreign, "stop")
    ctrl.run.assert_not_called()
    assert not any(m == "DELETE" for m, _, _ in rig.api.calls)


def test_entire_main_timer_including_cheap_and_storage_must_fit(rig):
    ctrl = rig.main(prior="13")
    with pytest.raises(ValueError, match="not funded"):
        ctrl.launch()
    assert not any(m == "POST" for m, _, _ in rig.api.calls)
    assert not ctrl.event("create-intent")


def test_all_in_deadlines_and_cost_accounting(rig):
    ctrl = rig.launch(rig.main())
    intent = ctrl.event("create-intent")["data"]
    assert c._utc(intent["deadline_utc"]) == UTC + timedelta(seconds=19200)
    assert c._utc(intent["hard_deadline_utc"]) == UTC + timedelta(seconds=19800)
    rig.advance(3600)
    rate = c._number(intent["quote"]["hourly_rate_usd"]) + c.base.STORAGE
    assert ctrl.cost_check(rig.api.pod) == rate
    last = ctrl.ledger.read()[-1]["data"]
    assert Decimal(last["cumulative_projected_usd"]) == Decimal(c.PRIOR_USD) + Decimal(".42") + Decimal(4260) * rate / 3600
    with pytest.raises(ValueError, match="deadline"):
        ctrl.cost_check(rig.api.pod, horizon=15600)


def test_restart_does_not_reset_elapsed_and_backward_clock_fails(rig):
    ctrl = rig.launch(rig.main())
    rig.advance(19000)
    ctrl.cost_check(rig.api.pod)
    restarted = rig.controller("main")
    rig.advance(140)
    with pytest.raises(ValueError, match="deadline"):
        restarted.cost_check(rig.api.pod)
    rig.now -= timedelta(seconds=1000)
    with pytest.raises(ValueError, match="clock"):
        restarted.cost_check(rig.api.pod)


def test_only_fifty_total_is_available_at_runtime_and_closure(rig):
    ctrl = rig.launch(rig.main())
    # Simulate provider/cleanup delay: prior-study caps cannot excuse an overrun.
    rig.advance(27000)
    with pytest.raises(ValueError, match="Budget"):
        ctrl.cost_check(rig.api.pod)
    closed = ctrl.terminate()["data"]
    assert Decimal(closed["cumulative_upper_bound_usd"]) > 50
    assert closed["within_limits"] is False


@pytest.mark.parametrize("horizon", [0, -1, True, float("nan")])
def test_invalid_horizon_fails_closed(rig, horizon):
    ctrl = rig.launch(rig.controller())
    with pytest.raises(ValueError):
        ctrl.cost_check(rig.api.pod, horizon)


@pytest.mark.parametrize("change", [{"cost": "99"}, {"gpu": None},
    {"gpu": {"id": "NVIDIA B200", "count": True, "memory": 180}}, {"image": "other"}])
def test_billing_or_hardware_drift_fails_closed(rig, change):
    ctrl = rig.launch(rig.main())
    with pytest.raises(ValueError):
        ctrl.cost_check({**rig.api.pod, **change})


def test_cheap_receipt_requires_pass_exit_hashes_and_direct_closure(rig):
    main = rig.controller("main")
    with pytest.raises(ValueError, match="qualification"):
        main.cheap_receipt()
    cheap = rig.qualified_cheap()
    assert main.cheap_receipt() == Decimal(cheap.event("closed")["data"]["compute_upper_bound_usd"])
    saved = json.loads((cheap.base / "final-retrieval.json").read_text())["data"]
    (Path(saved["directory"]) / "tests.xml").write_text("changed")
    with pytest.raises(ValueError, match="hashes"):
        main.cheap_receipt()


@pytest.mark.parametrize("bad", ["missing", "skipped", "failure", "error"])
def test_cuda_receipt_rejects_missing_or_skipped_tests(tmp_path, bad):
    xml = CUDA_XML
    if bad == "missing":
        xml = xml.replace("tests.test_dose_exposure_backend", "tests.unrelated")
    else:
        xml = xml.replace('name="test_cuda"/>', 'name="test_cuda"><' + bad + '/></testcase>')
    path = tmp_path / "tests.xml"
    path.write_text(xml)
    with pytest.raises(ValueError, match="CUDA"):
        c.check_cuda_tests(path)


@pytest.mark.parametrize("kind,seconds", [("cheap", 1200), ("main", 19200)])
def test_worker_window_shrinks_and_credentials_are_allowlisted(rig, kind, seconds):
    ctrl = rig.launch(rig.main() if kind == "main" else rig.controller())
    rig.advance(100)
    ctrl._ssh = Mock(return_value=b"")
    ctrl.start_worker()
    transfer = ctrl._ssh.call_args_list[1].kwargs["data"]
    assert transfer == (b"export HF_TOKEN=hf_dummy_test_only\n" if kind == "main" else b"export HF_TOKEN=''\n")
    dispatch = ctrl._ssh.call_args_list[-1].args[1]
    assert "env -i HOME=/root" in dispatch
    assert all(secret not in dispatch for secret in ("hf_dummy", "rp_dummy", "api_dummy", "RUNPOD_API_KEY", "OPENAI_API_KEY"))
    assert ctrl.event("worker-intent")["data"]["seconds"] == seconds - 100
    with pytest.raises(ValueError, match="disabled"):
        ctrl.start_worker()


def test_ambiguous_worker_dispatch_persists_identity_and_never_retries(rig):
    ctrl = rig.launch(rig.controller())
    ctrl._ssh = Mock(side_effect=[b"", b"", RuntimeError("Lost dispatch response")])
    with pytest.raises(RuntimeError):
        ctrl.start_worker()
    assert ctrl.event("worker-intent") and not ctrl.event("worker-started")
    with pytest.raises(ValueError, match="disabled"):
        ctrl.start_worker()
    assert ctrl.signal_worker.__func__ is c.CorrectedLifecycle.signal_worker


def test_worker_scripts_are_bash_valid_and_study_specific():
    for kind in ("cheap", "main"):
        script = c.worker_script(kind, RELATIVE, FREEZE, UTC.isoformat(), stub_plan())
        subprocess.run(["bash", "-n"], input=script.encode(), capture_output=True, check=True)
        assert "load_plan" in script and FREEZE in script
        assert "RUNPOD_API_KEY" not in script and "OPENAI_API_KEY" not in script
        assert "APPROVE" not in script
        if kind == "cheap":
            assert all(name in script for name in c.TESTS)
            assert "BERG_TEST_DEVICE=cuda" in script and "torch.cuda.is_bf16_supported()" in script
            assert "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1" in script
        else:
            assert "experiments.berg_dose_exposure.runner" in script
            assert all(flag in script for flag in ("--plan", "--freeze", "--out", "--cache", "--deadline-utc"))
        binding = {"worker_id": "b" * 32, "pod_id": "owned1", "plan_sha256": "c" * 64, "freeze_commit": FREEZE}
        dispatch = c.transport.dispatch_command(script, 1200, binding)
        subprocess.run(["bash", "-n"], input=dispatch.encode(), capture_output=True, check=True)
        assert "worker-closing.json" in dispatch and "worker-dispatch.lock" in dispatch


@pytest.mark.parametrize("path", ["../bad", "/absolute", "data/other/PLAN.json",
    "data/berg_dose_exposure/../PLAN.json", "data/berg_dose_exposure//PLAN.json", "data/berg_dose_exposure/a\n"])
def test_unsafe_worker_paths_rejected(path):
    with pytest.raises(ValueError):
        c.worker_script("main", path, FREEZE, UTC.isoformat(), stub_plan())


def bound_sparse_plan():
    from experiments.berg_dose_exposure import protocol
    sources = set(protocol.source_paths())
    inputs = protocol.INPUTS
    return {"budget": deepcopy(c.BUDGET),
            "source_hashes": {name: c.base.sha(c.ROOT / name) for name in sorted(sources)},
            "input_hashes": {name: c.base.sha(c.ROOT / name) for name in sorted(inputs)}}


def test_source_closure_includes_transitive_imports_and_package_initializers():
    from experiments.berg_dose_exposure import protocol
    paths = protocol.source_paths()
    assert paths == sorted(set(paths))
    assert set(c.SPARSE_REQUIRED_SOURCES) <= set(paths)
    assert {"experiments/automated_rubric_audit/__init__.py",
            "experiments/automated_rubric_audit/common.py",
            "tests/test_sae_assay_backend.py", "tests/test_sae_assay_controller.py"} <= set(paths)
    assert all((c.ROOT / name).is_file() for name in paths)
    assert not any(name.startswith("data/") for name in paths)


def test_sparse_checkout_contains_code_roots_and_exact_bound_data_before_checkout():
    from experiments.berg_dose_exposure import protocol
    plan = bound_sparse_plan()
    paths = c.sparse_paths(RELATIVE, plan)
    bound = set(plan["source_hashes"]) | set(plan["input_hashes"]) | {RELATIVE}
    assert set(paths) == set(c.SPARSE_CODE_ROOTS) | {
        name for name in bound if Path(name).parts[0] not in c.SPARSE_CODE_ROOTS}
    assert {"experiments", "src", "tests", RELATIVE, protocol.POWER,
            protocol.MAPPING, protocol.source.MATCHING} <= set(paths)
    assert {name for name in paths if name.startswith("data/")} == set(plan["input_hashes"]) | {RELATIVE}
    assert {name for name in paths if name.startswith("docs/")} <= set(plan["source_hashes"])
    assert {c.REQUIREMENTS, *c.TESTS} <= set(plan["source_hashes"])
    assert not {"data", "docs", "evidence", "paper"} & set(paths)
    assert not any("screen_precision_20260930" in name or "source_aligned_v1_20261001" in name for name in paths)
    for kind in ("cheap", "main"):
        script = c.worker_script(kind, RELATIVE, FREEZE, UTC.isoformat(), plan)
        # Only the code roots are directories; data patterns are exact files.
        sparse = next(line for line in script.splitlines() if " | git sparse-checkout " in line)
        assert sparse.endswith(" | git sparse-checkout set --no-cone --stdin")
        patterns = shlex.split(sparse.split(" | ", 1)[0])[2:]
        assert patterns == ["/" + name for name in paths]
        assert script.index("sparse-checkout set") < script.index("git checkout --detach")
        assert "--filter=blob:none --no-checkout --single-branch --no-tags --depth=1" in script
        assert "git fetch --depth=1 origin " + FREEZE in script
        assert 'test "$(git rev-parse HEAD)" = ' + FREEZE in script
        assert script.index("Sparse closure hash mismatch") < script.index(" -m pip install")
        assert "load_plan(" in script


@pytest.mark.parametrize("path", ["data", "data/", "../PLAN.json", "/absolute.json", ".env",
    "data/*/row.json", "data/[ab].json", "data/!row.json", "data/row\n.json", "data/../row.json",
    "out/row.json", "data/.private/row.json", "data/weights/model.json", "data/raw.safetensors", 1])
def test_unsafe_or_broad_sparse_binding_rejected(path):
    plan = stub_plan()
    plan["input_hashes"][path] = "d" * 64
    with pytest.raises(ValueError):
        c.sparse_paths(RELATIVE, plan)


def test_sparse_source_omission_blocks_rental(rig):
    rig.plan_data["source_hashes"].pop("experiments/operator_matching_fine/protocol.py")
    rig.plan.write_text(json.dumps(rig.plan_data))
    ctrl = rig.controller()
    with pytest.raises(ValueError, match="source closure"):
        ctrl.launch()
    assert not rig.api.calls and not ctrl.event("create-intent")


def test_sparse_worker_hash_check_rejects_changed_bound_input(tmp_path):
    plan = stub_plan()
    for group in ("source_hashes", "input_hashes"):
        for name in plan[group]:
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic bound input\n")
            plan[group][name] = c.base.sha(path)
    path = tmp_path / RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(c._canonical(plan) + b"\n")
    script = c.worker_script("main", RELATIVE, FREEZE, UTC.isoformat(), plan)
    check = next(line for line in script.splitlines() if line.startswith("python3 -c "))
    command = [sys.executable, *shlex.split(check)[1:]]
    subprocess.run(command, cwd=tmp_path, capture_output=True, check=True)
    power = next(iter(plan["input_hashes"]))
    (tmp_path / power).write_text("changed\n")
    failed = subprocess.run(command, cwd=tmp_path, capture_output=True)
    assert failed.returncode != 0 and b"Sparse closure hash mismatch" in failed.stderr


def test_required_cuda_test_files_run_from_sparse_copy_on_cpu(tmp_path):
    plan = bound_sparse_plan()
    for name in c.sparse_paths(RELATIVE, plan):
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if name == RELATIVE:
            destination.write_bytes(c._canonical(plan) + b"\n")
        elif name in c.SPARSE_CODE_ROOTS:
            shutil.copytree(c.ROOT / name, destination,
                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        else:
            shutil.copyfile(c.ROOT / name, destination)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(tmp_path),
           "BERG_TEST_DEVICE": "cpu", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "GIT_DIR": str(c.OPERATIONAL_ROOT / ".git")}
    for key in tuple(env):
        if key.endswith(("_TOKEN", "_API_KEY")):
            env.pop(key)
    check = ("from experiments.berg_dose_exposure import protocol; "
             "assert set(protocol.source_paths()) == " + repr(set(plan["source_hashes"])) + "; "
             "assert all(protocol.sha(protocol.ROOT/p)==h for p,h in "
             + repr({**plan["source_hashes"], **plan["input_hashes"]}) + ".items())")
    subprocess.run([sys.executable, "-B", "-c", check], cwd=tmp_path, env=env,
                   capture_output=True, text=True, check=True, timeout=30)
    result = subprocess.run([sys.executable, "-B", "-m", "pytest", *c.TESTS, "-q", "-p", "no:cacheprovider"],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr


def test_corrupt_snapshot_blocks_delete_and_resumes_worker(rig):
    ctrl = rig.launch(rig.controller())
    actions = rig.snapshot(ctrl, corrupt=True)
    with pytest.raises(ValueError, match="hashes"):
        ctrl.retrieve()
    assert actions == ["pause", "resume"]
    with pytest.raises(ValueError):
        ctrl.terminate()
    assert not any(m == "DELETE" for m, _, _ in rig.api.calls)


def test_failed_snapshot_resumes_worker(rig):
    ctrl = rig.launch(rig.controller())
    actions = rig.snapshot(ctrl, fail=True)
    with pytest.raises(RuntimeError, match="Retrieval"):
        ctrl.retrieve()
    assert actions == ["pause", "resume"]


def test_added_final_artifact_blocks_delete(rig):
    ctrl = rig.launch(rig.controller())
    rig.snapshot(ctrl)
    receipt = ctrl.retrieve(final=True)
    (Path(receipt["data"]["directory"]) / "extra.json").write_text("{}")
    with pytest.raises(ValueError, match="inventory"):
        ctrl.terminate()
    assert not any(m == "DELETE" for m, _, _ in rig.api.calls)


def test_deletion_requires_retrieval_direct404_and_full_inventory(rig):
    ctrl = rig.launch(rig.controller())
    actions = rig.snapshot(ctrl)
    rig.advance(100)
    closed = ctrl.terminate()["data"]
    assert actions == ["stop"]
    assert (ctrl.base / "final-retrieval.json").is_file()
    assert closed["get_status"] == 404 and closed["inventory_ids"] == ["foreign1"]
    assert closed["within_limits"]
    assert rig.api.calls[-3:] == [("DELETE", "/pods/owned1", None), ("GET", "/pods/owned1", None), ("GET", "/pods", None)]


@pytest.mark.parametrize("mode", ["delete_stays", "inventory_stays"])
def test_unverified_deletion_never_repeated(rig, mode):
    ctrl = rig.launch(rig.controller())
    setattr(rig.api, mode, True)
    for _ in range(2):
        with pytest.raises(ValueError):
            ctrl.terminate()
    assert not ctrl.event("closed")
    assert sum(m == "DELETE" for m, _, _ in rig.api.calls) == 1


@pytest.mark.parametrize("kind,elapsed,overdue", [("cheap", 1801, True), ("main", 9000, False), ("main", 19801, True)])
def test_cleanup_uses_instance_deadline_and_retains_failure(rig, kind, elapsed, overdue):
    ctrl = rig.launch(rig.main() if kind == "main" else rig.controller())
    rig.advance(elapsed)
    ctrl.terminate = Mock(side_effect=[RuntimeError("synthetic failure"), {"closed": True}])
    assert ctrl.close_until_verified() == {"closed": True}
    retry = [e["data"] for e in ctrl.ledger.read() if e["id"].startswith("cleanup-retry:")][0]
    assert retry["hard_deadline_exceeded"] is overdue and retry["hard_seconds"] == ctrl.hard_seconds


def test_audit_adapter_is_partial_and_no_new_barriers(monkeypatch):
    audit = Mock(return_value={"pass": True})
    monkeypatch.setattr(package, "analysis", SimpleNamespace(audit=audit), raising=False)
    assert c.audit(Path("raw"), {"test": True}) == {"pass": True}
    audit.assert_called_once_with(Path("raw"), {"test": True}, partial=True, settled=False)
    c.audit(Path("raw"), {"test": True}, settled=True)
    audit.assert_called_with(Path("raw"), {"test": True}, partial=True, settled=True)
    assert c.transport.BARRIERS == ("qualification", "first-five")


@pytest.mark.parametrize("name", c.transport.BARRIERS)
def test_approval_requires_hash_bound_snapshot_and_passing_audit(rig, monkeypatch, name):
    ctrl = rig.launch(rig.main())
    ctrl.ledger.bind("worker-started", {"utc": UTC.isoformat()})
    barrier = {"barrier": name, "rows": c.BARRIER_ROWS[name],
               "plan_sha256": ctrl.plan_hash, "freeze_commit": FREEZE}
    filename = "WAITING-" + name + ".json"
    directory = ctrl.base / "retrievals/barrier"
    directory.mkdir(parents=True)
    (directory / filename).write_text(json.dumps(barrier))
    receipt = ctrl.record("retrieval", {"pod_id": "owned1", "directory": str(directory),
                                      "artifacts": c.artifact_map(directory)})
    approvals = {}
    ctrl.status = Mock(return_value={"pod": rig.api.pod, "files": {filename: barrier, "_approvals": approvals}})
    ctrl._ssh = Mock(return_value=b"")
    report = {"pass": False}
    auditor = Mock(return_value=report)
    monkeypatch.setattr(c, "audit", auditor)
    with pytest.raises(ValueError, match="audit failed"):
        ctrl.approve(name, ctrl.plan_hash)
    ctrl._ssh.assert_not_called()
    report["pass"] = True
    if name == "first-five":
        with pytest.raises(ValueError, match="Untreated screen"):
            ctrl.approve(name, ctrl.plan_hash)
        for count in (16, 18):
            report.update(generations=count, zero_screen_pass=True)
            with pytest.raises(ValueError, match="exactly five treated"):
                ctrl.approve(name, ctrl.plan_hash)
        report.update(generations=17, zero_screen_pass=True)
        with pytest.raises(ValueError, match="Qualification"):
            ctrl.approve(name, ctrl.plan_hash)
        ctrl.ledger.bind("approved:qualification", {"plan_sha256": ctrl.plan_hash})
        approvals["APPROVE-qualification"] = ctrl.plan_hash
    with pytest.raises(ValueError):
        ctrl.approve(name, "f" * 64)
    result = ctrl.approve(name, ctrl.plan_hash)
    assert result["id"] == "approved:" + name
    assert ctrl._ssh.call_args.kwargs["data"] == (ctrl.plan_hash + "\n").encode()
    auditor.assert_called_with(directory, ctrl.plan, settled=True)
    assert ctrl.event("approval-intent:" + name)["data"]["retrieval_sha256"] == receipt["sha256"]


def test_main_creation_cannot_skip_cheap_checks(rig):
    ctrl = rig.controller("main")
    with pytest.raises(ValueError, match="qualification"):
        ctrl.launch()
    assert not rig.api.calls and not ctrl.event("create-intent")


def test_monitor_failed_audit_never_approves(rig, monkeypatch):
    ctrl = rig.launch(rig.main())
    ctrl.status = Mock(return_value={"pod": rig.api.pod, "files": {"WAITING-qualification.json": {}}})
    ctrl.retrieve = Mock(return_value={"data": {"directory": str(rig.root)}})
    ctrl.approve = Mock()
    ctrl.close_until_verified = Mock(return_value="closed")
    monkeypatch.setattr(c, "audit", Mock(return_value={"pass": False}))
    assert ctrl.monitor() == "closed"
    ctrl.approve.assert_not_called()


@pytest.mark.parametrize("state", ["awaiting_runner", "pending"])
def test_periodic_monitor_accepts_unsettled_snapshots_without_approval(rig, monkeypatch, state):
    ctrl = rig.launch(rig.main())
    ctrl.status = Mock(side_effect=[{"pod": rig.api.pod, "files": {}},
        {"pod": rig.api.pod, "files": {"DONE-all.json": {"pass": True}}}])
    ctrl.retrieve = Mock(return_value={"data": {"directory": str(rig.root)}})
    ctrl.approve = Mock()
    ctrl.close_until_verified = Mock(return_value="closed")
    auditor = Mock(return_value={"pass": True, "state": state, "receipt_complete": False,
        "pending_rows": [] if state == "awaiting_runner" else ["cal-1"], "pending_dispatches": []})
    monkeypatch.setattr(package, "analysis", SimpleNamespace(audit=auditor), raising=False)
    assert ctrl.monitor() == "closed"
    auditor.assert_called_once_with(rig.root, ctrl.plan, partial=True, settled=False)
    ctrl.approve.assert_not_called()
    assert rig.ticks == 60


@pytest.mark.parametrize("scientific,limit", [(False, 1800), (True, 900)])
def test_monitor_stalls_on_no_progress_despite_log_heartbeat(rig, monkeypatch, scientific, limit):
    ctrl = rig.launch(rig.main())
    progress = {"PLAN.json": [100, 1], "runtime.json": [100, 1]}
    if scientific:
        progress["rows/qualification-live.json"] = [100, 1]

    def status():
        return {"pod": rig.api.pod, "files": {"_progress": {
            **progress, "controller.log": [rig.ticks, rig.ticks],
            "progress.json": [rig.ticks, rig.ticks], "receipts.jsonl": [rig.ticks, rig.ticks]}}}

    ctrl.status = Mock(side_effect=status)
    ctrl.retrieve = Mock(return_value={"data": {"directory": str(rig.root)}})
    ctrl.close_until_verified = Mock(return_value="closed")
    monkeypatch.setattr(c, "audit", Mock(return_value={"pass": True}))
    assert ctrl.monitor() == "closed"
    assert rig.ticks == limit
    stalled = [r["data"] for r in ctrl.ledger.read() if r["id"].startswith("progress-stalled:")]
    assert len(stalled) == 1 and stalled[0]["limit_seconds"] == limit


def test_new_scientific_row_resets_only_scientific_stall_window(rig, monkeypatch):
    ctrl = rig.launch(rig.main())

    def status():
        progress = {"rows/qualification-live.json": [100, 1]}
        if rig.ticks >= 600:
            progress["rows/first.json"] = [100, 2]
        return {"pod": rig.api.pod, "files": {"_progress": progress}}

    ctrl.status = Mock(side_effect=status)
    ctrl.retrieve = Mock(return_value={"data": {"directory": str(rig.root)}})
    ctrl.close_until_verified = Mock(return_value="closed")
    monkeypatch.setattr(c, "audit", Mock(return_value={"pass": True}))
    assert ctrl.monitor() == "closed"
    assert rig.ticks == 600 + c.SCIENTIFIC_STALL_SECONDS


def test_cli_is_offline_by_default_and_env_file_never_printed(rig, capsys, monkeypatch):
    api = Mock(side_effect=AssertionError("No provider construction"))
    monkeypatch.setattr(c.base, "RunPodV2", api)
    c.main(["--plan", str(rig.plan), "--freeze", FREEZE, "--kind", "main",
            "--env-file", str(rig.root / "missing-private-env")])
    output = capsys.readouterr().out
    assert json.loads(output) == {"dry_run": True, "network_calls": 0, "budget": c.BUDGET}
    assert "private-env" not in output and not rig.out.exists()


def test_cli_loads_explicit_env_file_locally_and_monitors_launch(rig, monkeypatch, capsys):
    env = rig.root / "private.env"
    load_env = Mock()
    monkeypatch.setitem(sys.modules, "dotenv", SimpleNamespace(load_dotenv=load_env))
    fake = Mock()
    fake.monitor.return_value = {"closed": True}
    monkeypatch.setattr(c, "Controller", Mock(return_value=fake))
    monkeypatch.setattr(c.base, "RunPodV2", Mock(return_value=rig.api))
    c.main(["--plan", str(rig.plan), "--freeze", FREEZE, "--kind", "main", "--launch", "--env-file", str(env)])
    load_env.assert_called_once_with(env)
    assert [call[0] for call in fake.method_calls] == ["launch", "monitor"]
    assert json.loads(capsys.readouterr().out) == {"closed": True}
