"""Synthetic recovery fixtures only. No providers, credentials, SSH or GPUs."""
from copy import deepcopy
from decimal import Decimal
import json
import io
import shlex
import subprocess
from unittest.mock import Mock
import urllib.request

import pytest

from experiments.kolibri_bootstrap_a1 import adapter as a, production as p
from experiments.kolibri_swap import protocol, production as old, runtime
from experiments.openrouter_swap.ledger import Halted, Ledger
from tests.test_kolibri_swap_production import (NOW, FREEZE, PLAN_HASH, saved_controller,
    tree_hashes, write)
from tests.test_kolibri_swap_runtime import senders
from tests.test_kolibri_swap_controller import Clock, FakeAPI, saved_retrieval

CARRY = "0.08071909043333333333333333333"


@pytest.mark.parametrize("body", [b"", b"{", b'{"status":'])
@pytest.mark.parametrize("exited", [False, True])
def test_partial_smoke_is_pending_not_a_false_pass(tmp_path, monkeypatch, capsys, body, exited):
    (tmp_path / "gpu-smoke.json").write_bytes(body)
    if exited:
        write(tmp_path / "exit.json", {"exit_code": 143})
    monkeypatch.setattr(urllib.request, "urlopen", Mock(side_effect=OSError("synthetic offline")))
    code = shlex.split(a.status_command())[2].replace('/workspace/kolibri/out', str(tmp_path))
    exec(compile(code, '<synthetic-status>', 'exec'), {})
    result = json.loads(capsys.readouterr().out)
    assert result['pending_json'] == ['gpu-smoke.json']
    assert 'gpu-smoke.json' not in result
    assert result['incomplete_after_exit'] is exited
    assert result['ready'] is False


def test_complete_smoke_status_is_forwarded_exactly(tmp_path, monkeypatch, capsys):
    value = {'status': 'passed', 'synthetic': True}
    write(tmp_path / 'gpu-smoke.json', value)
    monkeypatch.setattr(urllib.request, 'urlopen', Mock(side_effect=OSError))
    code = shlex.split(a.status_command())[2].replace('/workspace/kolibri/out', str(tmp_path))
    exec(compile(code, '<synthetic-status>', 'exec'), {})
    result = json.loads(capsys.readouterr().out)
    assert result['gpu-smoke.json'] == value and not result['pending_json']


@pytest.mark.parametrize('success', [False, True])
def test_exactly_three_status_reads_with_budget_checks(success):
    ctl = object.__new__(a.Controller)
    ctl.get_pod = Mock(return_value={'id': 'synthetic'})
    ctl.cost_check, ctl.record, ctl.sleep = Mock(), Mock(), Mock()
    good = b'{"ready":false,"pending_json":["gpu-smoke.json"]}'
    ctl._ssh = Mock(side_effect=[RuntimeError('synthetic SSH'), b'{',
                                good if success else subprocess.TimeoutExpired('ssh', 30)])
    if success:
        assert ctl.status()['worker']['pending_json'] == ['gpu-smoke.json']
    else:
        with pytest.raises(RuntimeError, match='three bounded'):
            ctl.status()
    assert ctl._ssh.call_count == ctl.cost_check.call_count == ctl.get_pod.call_count == 3
    assert ctl.sleep.call_args_list == [((5,),), ((5,),)]
    assert all(call.kwargs['timeout'] == 30 for call in ctl._ssh.call_args_list)
    assert ctl.record.call_count == (2 if success else 3)


def test_budget_or_ownership_failure_is_not_retried():
    ctl = object.__new__(a.Controller)
    ctl.get_pod, ctl._ssh = Mock(return_value={}), Mock()
    ctl.cost_check = Mock(side_effect=Halted('budget'))
    with pytest.raises(Halted):
        ctl.status()
    assert ctl.get_pod.call_count == 1 and not ctl._ssh.called


def test_monitor_waits_through_in_progress_report_then_closes():
    ctl = object.__new__(a.Controller)
    ctl.api, ctl.kind = Mock(writable=True), 'cheap'
    ctl.event = Mock(return_value=None)
    ctl.status = Mock(side_effect=[
        {'pod': {'id':'synthetic'}, 'worker': {'pending_json':['gpu-smoke.json'], 'ready':False}},
        {'pod': {'id':'synthetic'}, 'worker': {'gpu-smoke.json':{'status':'passed'},
                                            'exit.json':{'exit_code':0}, 'ready':False}}])
    ctl.record, ctl.cost_check = Mock(), Mock()
    ctl.terminate = Mock(return_value={'synthetic_closed':True})
    def sleep(seconds):
        assert seconds == 30 and not ctl.terminate.called
    ctl.sleep = sleep
    # No stop marker; its parent is an inert synthetic nonexistent path.
    from pathlib import Path
    ctl.base = Path('/synthetic-no-kolibri-stop-marker')
    assert ctl.monitor() == {'synthetic_closed':True}
    assert ctl.terminate.call_count == 1 and ctl.status.call_count == 2


@pytest.mark.parametrize('spent,accept', [('0.90', True), ('1.10', False)])
def test_cheap_reserve_includes_exact_predecessor(monkeypatch, spent, accept):
    ctl = object.__new__(a.Controller)
    ctl.kind, ctl.amendment = 'cheap', {'predecessor': {'cost_usd': CARRY}}
    monkeypatch.setattr(a.old.Controller, 'cost_check', lambda *args: Decimal(spent))
    if accept:
        assert ctl.cost_check({'cost': '.74'}) == Decimal(spent)
    else:
        with pytest.raises(Halted, match='Cumulative cheap'):
            ctl.cost_check({'cost': '.74'})


@pytest.fixture
def repair(tmp_path, monkeypatch):
    original_bytes = (protocol.ROOT/protocol.PLAN).read_bytes()
    plan = protocol.verify(protocol.ROOT / protocol.PLAN)
    repo, root = tmp_path/'repo', tmp_path/'run/bootstrap-a1'
    source = repo/'repair.py'
    source.parent.mkdir()
    source.write_text('# Synthetic repair binding\n')
    (repo/protocol.PLAN).parent.mkdir(parents=True)
    (repo/protocol.PLAN).write_bytes(original_bytes)
    amendment = {'source_hashes': {'repair.py': protocol.sha(source)},
                 'predecessor': {'cost_usd': CARRY}}
    write(repo/a.AMENDMENT, amendment)
    monkeypatch.setattr(protocol, 'ROOT', repo)
    return plan, root, amendment


def bind_controllers(root, amendment):
    for kind in ('cheap', 'main'):
        ledger = saved_controller(root, kind, closed=kind == 'cheap')
        ledger.bind('controller:config', {'amendment_sha256': protocol.sha(protocol.ROOT/a.AMENDMENT),
                                          'prior_cheap_usd': amendment['predecessor']['cost_usd']})


def test_new_controller_uses_separate_ledger_and_forbids_old_pod(tmp_path, monkeypatch, repair):
    plan, root, amendment = repair
    old_root = root.parent
    write(old_root/'controller/cheap/events.jsonl', {'synthetic': 'unchanged predecessor'})
    before = tree_hashes(old_root/'controller')
    monkeypatch.setattr(a, 'verify', lambda freeze: amendment)
    monkeypatch.setattr(protocol, 'verify', lambda path: plan)
    monkeypatch.setattr(a.old, 'canonical_root', lambda: old_root)
    ctl = a.Controller(FREEZE, 'cheap', Mock(), clock=lambda: NOW)
    assert ctl.base == root/'controller/cheap'
    assert before == tree_hashes(old_root/'controller')
    assert ctl.event('controller:config')['data']['prior_cheap_usd'] == CARRY
    assert not ctl._new_pod({'id': a.FAILED_POD}, {})


def test_one_new_cheap_attempt_closes_without_resetting_predecessor(repair, monkeypatch):
    plan, root, amendment = repair
    clock = Clock()
    class CheapAPI(FakeAPI):
        def request(self, method, path, body=None):
            status, value = super().request(method, path, body)
            if method == 'POST':
                self.pod['cost'] = value['cost'] = '.74'
            return status, value
    api = CheapAPI(clock)
    monkeypatch.setattr(a, 'verify', lambda freeze: amendment)
    monkeypatch.setattr(protocol, 'verify', lambda path: plan)
    monkeypatch.setattr(a.old, 'canonical_root', lambda: root.parent)
    monkeypatch.setattr(a.old, 'quote', lambda api, kind: {'hourly_rate_usd':'.74','storage_hourly_usd':'.10'})
    monkeypatch.setattr(a.old.urllib.request, 'urlopen', lambda *args, **kwargs:
                        io.BytesIO((protocol.ROOT/protocol.PLAN).read_bytes()))
    key = protocol.ROOT/'synthetic-key'
    key.write_text('synthetic fixture, not a credential')
    key.with_suffix('.pub').write_text('ssh-ed25519 AAAA synthetic')
    monkeypatch.setattr(a.old.base, 'KEY', key)
    ctl = a.Controller(FREEZE, 'cheap', api, clock=clock, sleep=clock.sleep)
    ctl.start_worker = Mock()
    ctl.launch()
    assert api.calls.count(('POST','/pods')) == 1 and ctl.start_worker.call_count == 1
    with pytest.raises(ValueError, match='already attempted'):
        ctl.launch()
    saved_retrieval(ctl)
    clock.sleep(60)
    closed = ctl.terminate()
    assert closed['data']['get_status'] == 404
    assert Decimal(closed['data']['compute_upper_bound_usd']) + Decimal(CARRY) < Decimal('1.25')
    assert api.calls.count(('DELETE','/pods/kolibri-owned-1')) == 1
    assert api.calls[-1] == ('GET','/pods/kolibri-owned-1')
    assert ctl.amendment['predecessor']['cost_usd'] == CARRY


def test_bound_production_fixtures_include_carry_and_keep_science(repair):
    plan, root, amendment = repair
    bind_controllers(root, amendment)
    local, judge, generated, judged = senders()
    with Ledger(root/'collection/judges', cap='45', screen_cap='10') as ledger, \
            runtime.ReceiptJournal(root/'collection/http', FREEZE, PLAN_HASH) as receipts:
        runner = p.Runner(plan, FREEZE, PLAN_HASH, ledger, receipts, local, judge, amendment=amendment)
        runner.guard = a.StudyGuard(root, plan, FREEZE, PLAN_HASH, ledger,
                                   amendment=amendment, clock=lambda: NOW)
        baseline = old.StudyGuard(root, plan, FREEZE, PLAN_HASH, ledger, clock=lambda: NOW)
        assert runner.guard.state()['gpu_usd'] == baseline.state()['gpu_usd'] + Decimal(CARRY)
        assert old.phase(runner, 'fixtures', root)['pass']
        assert len(generated) == 1 and len(judged) == 24
        assert generated[0] == runtime.local_request(plan['models']['kolibri'], 'route:kolibri',
                                                    [{'role':'user','content':'Reply with exactly OK.'}])
        assert runner.audit()['calls'] == 25
        (protocol.ROOT/'repair.py').write_text('# Changed technical source\n')
        with pytest.raises(Halted, match='Technical repair changed'):
            runner.generate_blocks('screen', initial=True)


@pytest.mark.parametrize('mutation', ['carry', 'binding'])
def test_production_rejects_carry_overrun_or_foreign_cheap(repair, mutation):
    plan, root, amendment = repair
    bind_controllers(root, amendment)
    if mutation == 'carry':
        amendment = deepcopy(amendment)
        amendment['predecessor']['cost_usd'] = '1.01'
    else:
        write(protocol.ROOT/a.AMENDMENT, {'synthetic':'different technical binding'})
    with Ledger(root/'collection/judges', cap='45', screen_cap='10') as ledger:
        with pytest.raises(Halted):
            a.StudyGuard(root, plan, FREEZE, PLAN_HASH, ledger, amendment=amendment, clock=lambda: NOW)


def test_main_forecast_receives_gpu_carry(repair):
    plan, root, amendment = repair
    bind_controllers(root, amendment)
    with Ledger(root/'judges', cap='45', screen_cap='10') as ledger:
        guard = a.StudyGuard(root, plan, FREEZE, PLAN_HASH, ledger, amendment=amendment, clock=lambda: NOW)
        runner = Mock()
        runner.main_admission.return_value = {'main_seconds_with_margin': '600'}
        guard.admission(runner)
        assert Decimal(runner.main_admission.call_args.kwargs['gpu_spent_usd']) == guard.state()['gpu_usd']
        assert guard.state()['prior_cheap_usd'] == Decimal(CARRY)


def test_failed_or_incomplete_cheap_never_qualifies_main(repair, monkeypatch):
    _, root, amendment = repair
    bind_controllers(root, amendment)
    ctl = object.__new__(a.Controller)
    ctl.out, ctl.plan_hash, ctl.freeze = root, PLAN_HASH, FREEZE
    ctl.amendment, ctl.amendment_hash = amendment, protocol.sha(protocol.ROOT/a.AMENDMENT)
    monkeypatch.setattr(a.old.Controller, 'cheap_pass', lambda self: {})
    # Even if an old helper only checked a shallow status, A1 requires the full receipt.
    monkeypatch.setattr(old, 'closed_receipt', Mock(side_effect=Halted('Incomplete smoke')))
    with pytest.raises(Halted, match='Incomplete smoke'):
        ctl.cheap_pass()


def test_candidate_does_not_rebuild_science_or_write_plan(monkeypatch):
    path = protocol.ROOT/protocol.PLAN
    before = path.read_bytes()
    monkeypatch.setattr(a, 'predecessor', lambda: {'cost_usd': CARRY, 'synthetic': True})
    result = a.build()
    assert result['cheap_remaining_usd'] == str(Decimal('1.25')-Decimal(CARRY))
    assert result['scientific_plan_sha256'] == a.ORIGINAL_PLAN_SHA
    assert not result['science_changed'] and path.read_bytes() == before
    original = protocol.verify(path)['source_hashes']
    assert len(original) == 90 and not set(original) & set(result['source_hashes'])


def test_amendment_tamper_rejected_before_remote_proof(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol, 'ROOT', tmp_path)
    write(tmp_path/a.AMENDMENT, {'schema':'tampered'})
    monkeypatch.setattr(a, 'build', lambda: {'schema':'expected'})
    remote = Mock(side_effect=AssertionError('no network'))
    monkeypatch.setattr(protocol, 'verify', remote)
    with pytest.raises(Halted, match='binding differs'):
        a.verify(FREEZE)
    assert not remote.called


@pytest.mark.parametrize('args', [['--phase','fixtures'],
    ['--phase','fixtures','--execute','--run-dir','/tmp/other'],
    ['--phase','audit','--execute']])
def test_cli_authority_and_root_guards_precede_credentials(args, monkeypatch):
    verify = Mock(side_effect=AssertionError('no verification reached'))
    monkeypatch.setattr(a, 'verify', verify)
    with pytest.raises(SystemExit) as exc:
        p.main(['--freeze',FREEZE,*args])
    assert exc.value.code == 1 and not verify.called
