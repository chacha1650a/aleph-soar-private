"""S1 scheduling, stop-on-error, evidence and preflight boundaries; no sockets."""
import json
from types import SimpleNamespace

import pytest

from tools import s1_input_probe as probe


class FakeClient:
    created = []
    fail_at = None
    fail_status = 429
    csrf_fail_at = None

    def __init__(self, host, port, source):
        assert (host, port) == ('203.0.113.1', 80)
        assert source in ('203.0.113.11', '203.0.113.13', '203.0.113.14',
                          '203.0.113.15', '203.0.113.16')
        self.source = source
        self.history = []
        self.on_record = None
        self.failures = 0
        self.created.append(self)

    def get_csrf(self):
        number = sum(item['method'] == 'GET' for item in self.history) + 1
        status = 403 if number == self.csrf_fail_at else 200
        self.history.append({'method': 'GET', 'status': status})
        self.on_record()
        if status == 403:
            raise RuntimeError('secret-canary-cookie-password')

    def fail_login(self, username, password):
        assert username.startswith('zz_') and password.startswith('wrong_test_')
        self.failures += 1
        self.history.append({'method': 'POST', 'status': self.fail_status if self.failures == self.fail_at else 401})
        self.on_record()
        if self.failures == self.fail_at:
            raise RuntimeError('secret-canary-cookie-password')


@pytest.fixture(autouse=True)
def reset():
    FakeClient.created = []
    FakeClient.fail_at = None
    FakeClient.fail_status = 429
    FakeClient.csrf_fail_at = None


def test_plan_sends_nothing_and_rejects_non_test_accounts(monkeypatch, capsys):
    monkeypatch.setattr(probe, 'preflight', lambda: pytest.fail('plan called preflight'))
    assert probe.main(['--run-id', 's1-test']) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['maximum_http_requests'] == 22
    assert plan['maximum_login_attempts'] == 11
    assert plan['minimum_first_to_last_seconds'] == 1000
    assert plan['minimum_first_to_ninth_seconds'] == 800
    with pytest.raises(ValueError):
        probe.make_plan('s1-test', 'administrator')


@pytest.mark.parametrize('source,interval', [('203.0.113.11', 100), ('203.0.113.13', 100), ('203.0.113.11', 200)])
def test_bounded_eleven_attempts_and_intervals_with_no_secrets(tmp_path,source,interval):
    seconds = [0]
    waits = []
    def sleep(delay):
        waits.append(delay)
        seconds[0] += delay
    path = tmp_path / 'evidence.json'
    result = probe.run(probe.make_plan('s1-test', 'zz_a1', source=source, interval=interval), path, FakeClient,
                       sleeper=sleep, monotonic=lambda: seconds[0])
    assert waits == [interval] * 10
    assert result['completed_failures'] == 11 and len(result['http_requests']) == 22
    assert result['login_post_attempts'] == result['login_posts_with_response'] == 11
    assert FakeClient.created[0].source == source
    assert result['state'] == 'inputs_finished_external_evidence_pending'
    assert not result['graylog_detection_verified'] and not result['restoration_verified']
    assert 'wrong_test_' not in path.read_text()
    assert not list(tmp_path.glob('evidence.json.*'))


def test_unexpected_response_stops_without_retry_or_raw_exception(tmp_path):
    FakeClient.fail_at = 3
    path = tmp_path / 'evidence.json'
    result = probe.run(probe.make_plan('s1-test', 'zz_a1'), path, FakeClient, sleeper=lambda _: None)
    assert result['state'] == 'aborted_no_automatic_retry'
    assert result['completed_failures'] == 2
    assert FakeClient.created[0].failures == 3
    assert len(result['http_requests']) == 6
    assert 'secret-canary' not in path.read_text()


@pytest.mark.parametrize('stage', ['csrf', 'login'])
def test_http403_stops_without_filling_eleven_or_claiming_effect(tmp_path,stage):
    if stage == 'csrf':
        FakeClient.csrf_fail_at = 3
    else:
        FakeClient.fail_at = 3
        FakeClient.fail_status = 403
    path=tmp_path/'stopped.json'
    result=probe.run(probe.make_plan('s1-stop','zz_a1'),path,FakeClient,sleeper=lambda _:None)
    assert result['state']=='stopped_http403_effect_verification_pending'
    assert result['completed_failures']==2
    assert result['login_post_attempts']==result['login_posts_with_response']==(2 if stage=='csrf' else 3)
    assert result['stopped_request_method']==('GET' if stage=='csrf' else 'POST')
    assert not result['block_effect_verified'] and not result['live_n8n_verified']
    assert 'secret-canary' not in path.read_text()


@pytest.mark.parametrize('changes', [
    {'source':'203.0.113.12'}, {'source':'203.0.113.100'}, {'source':'198.51.100.10'},
    {'attempts':12}, {'attempts':0}, {'attempts':True}, {'attempts':8},
    {'interval':1}, {'interval':99}, {'interval':False},
])
def test_plan_rejects_normal_sources_unbounded_counts_and_unagreed_intervals(changes):
    with pytest.raises(ValueError):
        probe.make_plan('s1-invalid','zz_a1',**changes)


def test_mutated_plan_is_rejected_before_any_request(tmp_path):
    plan=probe.make_plan('s1-invalid','zz_a1')
    plan['maximum_login_attempts']=100
    with pytest.raises(ValueError):
        probe.run(plan,tmp_path/'never-created.json',FakeClient)
    assert not FakeClient.created and not (tmp_path/'never-created.json').exists()


def test_existing_evidence_prevents_any_client_creation(tmp_path):
    path = tmp_path / 'evidence.json'
    path.write_text('keep')
    with pytest.raises(FileExistsError):
        probe.run(probe.make_plan('s1-test', 'zz_a1'), path, FakeClient)
    assert path.read_text() == 'keep' and not FakeClient.created


def test_interruption_preserves_partial_evidence(tmp_path):
    def interrupt(_):
        raise KeyboardInterrupt()
    result = probe.run(probe.make_plan('s1-test', 'zz_a1'), tmp_path / 'evidence.json',
                       FakeClient, sleeper=interrupt)
    assert result['completed_failures'] == 1
    assert result['reason'] == 'operator_interrupted'


@pytest.mark.parametrize('condition', ['ntp', 'source', 'route', 'hash'])
def test_failed_preflight_never_imports_or_calls_http(monkeypatch, condition):
    monkeypatch.setattr(probe.sys, 'platform', 'linux')
    def read(args, **kwargs):
        if args[0] == 'timedatectl':
            return 'no' if condition == 'ntp' else 'yes'
        if 'addr' in args:
            return json.dumps([{'addr_info': [{'local': probe.SOURCE,
                               'prefixlen': 24 if condition == 'source' else 32}]}])
        return json.dumps([{'dev': 'tun0' if condition == 'route' else 'eth0', 'from': probe.SOURCE}])
    monkeypatch.setattr(probe.subprocess, 'check_output', read)
    monkeypatch.setattr(probe, 'BASE', SimpleNamespace(read_bytes=lambda: b'changed client'))
    monkeypatch.setattr(probe.importlib.util, 'spec_from_file_location', lambda *a: pytest.fail('import on failed preflight'))
    with pytest.raises(ValueError):
        probe.preflight()


def test_boundary8_exact_cap_and_external_verdict(tmp_path):
    waits = []
    result = probe.run(probe.make_plan('s1-boundary', 'zz_a1', attempts=8,
                                      profile='boundary8'),
                       tmp_path/'boundary.json', FakeClient,
                       sleeper=waits.append, monotonic=lambda: 0)
    assert result['completed_failures'] == 8
    assert len(result['http_requests']) == 16
    assert result['login_post_attempts'] == 8
    assert waits == [100]*7
    assert result['plan']['minimum_first_to_last_seconds'] == 700
    assert result['plan']['minimum_first_to_ninth_seconds'] is None
    assert result['state'] == 'boundary_inputs_finished_non_detection_unverified'
    assert not result['non_detection_verified']
    assert not result['plan']['expected_detection']


@pytest.mark.parametrize('stage', ['csrf', 'login'])
def test_boundary403_is_unexpected_and_stops_without_more_requests(tmp_path, stage):
    if stage == 'csrf':
        FakeClient.csrf_fail_at = 2
    else:
        FakeClient.fail_at, FakeClient.fail_status = 2, 403
    result = probe.run(probe.make_plan('s1-boundary', 'zz_a1', attempts=8,
                                      profile='boundary8'),
                       tmp_path/'boundary.json', FakeClient, sleeper=lambda _: None)
    assert result['state'] == 'unexpected_http403_boundary_external_review'
    assert result['completed_failures'] == 1
    assert len(result['http_requests']) == (3 if stage == 'csrf' else 4)
    assert not result['non_detection_verified']


def test_boundary_cli_defaults_to_eight_without_network(monkeypatch, capsys):
    monkeypatch.setattr(probe, 'preflight', lambda *_: pytest.fail('plan called preflight'))
    assert probe.main(['--run-id', 's1-boundary', '--profile', 'boundary8']) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['maximum_login_attempts'] == 8 and plan['maximum_http_requests'] == 16
    with pytest.raises(SystemExit) as error:
        probe.main(['--run-id', 's1-boundary', '--profile', 'boundary8', '--attempts', '9'])
    assert error.value.code == 2


def test_boundary_tampered_attempts_rejected_before_evidence_or_client(tmp_path):
    plan = probe.make_plan('s1-boundary', 'zz_a1', attempts=8, profile='boundary8')
    plan['maximum_login_attempts'] = 9
    with pytest.raises(ValueError):
        probe.run(plan, tmp_path/'boundary.json', FakeClient)
    assert not FakeClient.created and not (tmp_path/'boundary.json').exists()


@pytest.mark.parametrize('source,username,profile,attempts', [
    ('203.0.113.14', 'zz_s1_1029_r1', 'trigger', 11),
    ('203.0.113.15', 'zz_s1_1029_r2', 'trigger', 11),
    ('203.0.113.16', 'zz_s1_1029_b8', 'boundary8', 8),
])
def test_tomorrow_sources_accounts_and_exact_request_counts(tmp_path, source, username, profile, attempts):
    waits=[]
    result=probe.run(probe.make_plan('s1-tomorrow', username, source, attempts, 100, profile),
                     tmp_path/'trial.json', FakeClient, sleeper=waits.append, monotonic=lambda:0)
    assert result['completed_failures']==attempts
    assert result['login_post_attempts']==attempts
    assert len(result['http_requests'])==attempts*2
    assert waits==[100]*(attempts-1)
    assert FakeClient.created[0].source==source
    assert not result['non_detection_verified']
    if profile=='boundary8':
        assert result['plan']['boundary_observation_seconds']==1860
        assert result['plan']['boundary_observation_from']=='eighth_401_arrival_at_graylog'
        assert result['state']=='boundary_inputs_finished_non_detection_unverified'


@pytest.mark.parametrize('source', ['203.0.113.12','203.0.113.100','203.0.113.17','.14','203.0.113.14/32'])
def test_boundary_rejects_normal_unassigned_or_partial_sources_before_client(tmp_path, source):
    with pytest.raises(ValueError):
        plan=probe.make_plan('s1-boundary', 'zz_s1_1029_b8', source, 8, 100, 'boundary8')
        probe.run(plan,tmp_path/'none.json',FakeClient)
    assert not FakeClient.created and not (tmp_path/'none.json').exists()


def test_separate_r2_boundary_evidence_cannot_change_each_others_counts(tmp_path):
    for source,account,profile,count,name in [
        ('203.0.113.15','zz_s1_1029_r2','trigger',11,'r2'),
        ('203.0.113.16','zz_s1_1029_b8','boundary8',8,'b8'),
    ]:
        probe.run(probe.make_plan(name,account,source,count,100,profile),
                  tmp_path/(name+'.json'),FakeClient,sleeper=lambda _:None)
    r2=json.loads((tmp_path/'r2.json').read_text())
    b8=json.loads((tmp_path/'b8.json').read_text())
    assert r2['completed_failures']==11 and b8['completed_failures']==8
    assert r2['plan']['username']!=b8['plan']['username']
    assert r2['plan']['source']!=b8['plan']['source']


@pytest.mark.parametrize('condition',['source','route','ntp'])
def test_tomorrow_preflight_uses_selected_source_without_fallback(monkeypatch,condition):
    monkeypatch.setattr(probe.sys,'platform','linux')
    selected='203.0.113.16'
    def read(args,**kwargs):
        if 'addr' in args:
            return json.dumps([{'addr_info':[{'local':selected if condition!='source' else probe.SOURCE,'prefixlen':32}]}])
        if 'route' in args:
            assert args[-1]==selected
            return json.dumps([{'dev':'eth0','from':selected if condition!='route' else probe.SOURCE}])
        return 'no' if condition=='ntp' else 'yes'
    monkeypatch.setattr(probe.subprocess,'check_output',read)
    monkeypatch.setattr(probe.importlib.util,'spec_from_file_location',lambda *a:pytest.fail('unexpected import'))
    with pytest.raises(ValueError): probe.preflight(selected)


def test_boundary_ninth_attempt_rejected_by_cli_before_preflight(monkeypatch,tmp_path):
    monkeypatch.setattr(probe,'preflight',lambda *_:pytest.fail('invalid count reached preflight'))
    with pytest.raises(SystemExit) as error:
        probe.main(['--run-id','b8','--username','zz_s1_1029_b8','--source','203.0.113.16',
                    '--profile','boundary8','--attempts','9','--execute','--output',str(tmp_path/'none.json')])
    assert error.value.code==2 and not FakeClient.created
