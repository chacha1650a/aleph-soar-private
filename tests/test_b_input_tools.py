"""Synthetic HTTP adapters only: no lab network, credentials or backend dependency."""
from datetime import datetime, timedelta, timezone
import hashlib
import http.client  # Load ssl before the network-denying fixture replaces socket.socket.
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    spec = importlib.util.spec_from_file_location('input_under_test', ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket
    def deny(*args, **kwargs):
        raise AssertionError('Real network forbidden in input tool tests')
    monkeypatch.setattr(socket, 'socket', deny)
    monkeypatch.setattr(socket, 'create_connection', deny)


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.connections = []
        self.bad_source = False

    def connection(self, host, port, timeout, source_address):
        owner = self
        class Connection:
            def connect(self):
                self.sock = SimpleNamespace(getsockname=lambda: (
                    '127.0.0.9' if owner.bad_source else source_address[0], 12345))

            def request(self, method, path, body=None, headers=None):
                owner.calls.append((method, path, body, headers))

            def getresponse(self):
                response = owner.responses.pop(0)
                if isinstance(response, Exception):
                    raise response
                return response

            def close(self):
                self.closed = True
        c = Connection()
        c.closed = False
        self.connections.append(c)
        return c


def reply(status=200, data=None, cookie=None, raw=None):
    payload = raw if raw is not None else json.dumps({
        'success': status != 401, 'data': {} if data is None else data}).encode()
    return SimpleNamespace(status=status, read=lambda limit: payload[:limit],
        getheaders=lambda: [('Set-Cookie', 'haedam_session=' + cookie)] if cookie else [])


def s4_responses():
    user = {'username': 'zz_s4_1103', 'role': 'staff'}
    normal = {'username': 'zz_n1', 'role': 'staff'}
    return [reply(data={'csrf_token': 'SYNTHETIC-CSRF'}, cookie='SYNTHETIC-ANON'),
            *[reply(401) for _ in range(5)],
            reply(data={'user': user}, cookie='SYNTHETIC-ORIGINAL'),
            reply(data={'user': None, 'csrf_token': 'SYNTHETIC-CSRF'}, cookie='SYNTHETIC-REPLACED'),
            reply(401),
            reply(data={'csrf_token': 'SYNTHETIC-CSRF'}, cookie='SYNTHETIC-NORMAL'),
            reply(data={'user': normal}), reply(data={'items': []}),
            reply(data={'logged_out': True}), reply(data={'user': None}),
            reply(data={'user': user}, cookie='SYNTHETIC-NEW'), reply(data={'logged_out': True})]


def prepare_s4(monkeypatch, responses=None):
    m = load('lab/s1s4/s4_session_check.py')
    wire = Transport(s4_responses() if responses is None else responses)
    monkeypatch.setattr(m.http.client, 'HTTPConnection', wire.connection)
    monkeypatch.setattr(m, 'INTERVAL', 0)
    return m, wire


@pytest.mark.parametrize('method', ['reset', 'keep'])
def test_s4_full_checks_keep_original_cookie_and_no_secrets(tmp_path, monkeypatch, method):
    m, wire = prepare_s4(monkeypatch)
    out = tmp_path / 'result.json'
    result = m.run(out, method, 'SYNTHETIC-PASSWORD', 'SYNTHETIC-NORMAL-PASSWORD',
        gate=lambda prompt: 'LOCKED' if 'type LOCKED' in prompt else 'UNLOCKED',
        reset_password=lambda: 'SYNTHETIC-RESET-PASSWORD')
    assert result['complete'] and len(result['steps']) == 16
    assert all(result['checks'].values())
    assert wire.calls[7][3]['Cookie'] == wire.calls[13][3]['Cookie'] == 'haedam_session=SYNTHETIC-ORIGINAL'
    assert not any('/response/' in x[1] or '/admin/' in x[1] for x in wire.calls)
    assert all(c.closed for c in wire.connections)
    assert 'SYNTHETIC-' not in out.read_text()
    before = out.read_bytes()
    with pytest.raises(FileExistsError):
        m.run(out, method, 'x', 'y')
    assert out.read_bytes() == before and len(wire.calls) == 16


@pytest.mark.parametrize('failure', ['old_session_valid', 'revived_session', 'rate_limit', 'logout_failure', 'normal_failure'])
def test_s4_failure_never_claims_complete_or_retries(tmp_path, monkeypatch, failure):
    responses = s4_responses()
    if failure == 'old_session_valid':
        responses[7] = reply(data={'user': {'username': 'zz_s4_1103'}})
        responses[8] = reply(data={'logged_out': True})  # One failure-cleanup logout.
    elif failure == 'revived_session':
        responses[13] = reply(data={'user': {'username': 'zz_s4_1103'}})
        responses[14] = reply(data={'logged_out': True})
    elif failure == 'rate_limit':
        responses[3] = reply(429)
    elif failure == 'logout_failure':
        responses[12] = reply(503)
    else:
        responses[10] = reply(401)
    m, wire = prepare_s4(monkeypatch, responses)
    result = m.run(tmp_path / 'r.json', 'reset', 'x', 'y',
        gate=lambda prompt: 'LOCKED' if 'type LOCKED' in prompt else 'UNLOCKED', reset_password=lambda: 'z')
    assert not result['complete'] and result['error_type'] == 'ValueError'
    assert result['automatic_retries'] == 0
    assert not any(x[1].startswith('/response/') for x in wire.calls)
    assert len([x for x in result['steps'] if x['phase'] == 'normal_logout']) <= 1
    if failure == 'rate_limit':
        assert len(wire.calls) == 4
    if failure == 'logout_failure':
        assert len(wire.calls) == 13


def test_s4_start_gate_and_default_no_io(monkeypatch, capsys):
    m = load('lab/s1s4/s4_session_check.py')
    monkeypatch.setattr(m.sys, 'argv', ['s4'])
    assert m.main() == 0 and 'PLAN ONLY' in capsys.readouterr().out
    start = datetime(2026, 11, 3, 15, 40, tzinfo=timezone(timedelta(hours=9)))
    with pytest.raises(ValueError, match='start_window_missed'):
        m.wait_for_start(start, start + timedelta(seconds=10), now=lambda: start + timedelta(seconds=11))
    times = iter([start-timedelta(seconds=1), start])
    sleeps = []
    m.wait_for_start(start, start+timedelta(seconds=10), now=lambda: next(times), sleep=sleeps.append)
    assert sleeps == [0.5]


@pytest.mark.parametrize('case', ['S8', 'S10'])
def test_s8s10_bounded_input_and_secrets(case):
    m = load('tools/s8s10_input.py')
    plan = m.make_plan(case, 'SYNTHETIC-ROUND', 'http://10.250.0.2:5000')
    wire = Transport([reply(404), reply(data={'csrf_token': 'SYNTHETIC-CSRF'}, cookie='SYNTHETIC-COOKIE'), reply(401)])
    pings, snapshots = [], []
    def ping(args, **kwargs):
        pings.append(args)
        return SimpleNamespace(returncode=1)
    result = m.execute(plan, lambda x: snapshots.append(json.dumps(x)), connection_factory=wire.connection, ping=ping)
    assert result['complete'] and not result['external_detection_response_verified']
    assert len(wire.calls) == 3 and len(pings) == (case == 'S10')
    if pings:
        assert pings[0] == ['ping', '-n', '-I', '203.0.113.22', '-c', '1', '-W', '1', '203.0.113.1']
        assert result['icmp']['block_log_verified'] is False
    assert all('SYNTHETIC-CSRF' not in s and 'SYNTHETIC-COOKIE' not in s and 'Synthetic-wrong-' not in s for s in snapshots)
    assert all(c.closed for c in wire.connections)


@pytest.mark.parametrize('failure', ['wrong_status', 'missing_csrf', 'timeout', 'source', 'large_response'])
def test_s8s10_stops_without_retry_or_icmp(failure):
    m = load('tools/s8s10_input.py')
    responses = [reply(404), reply(data={})]
    if failure == 'wrong_status': responses[0] = reply(200)
    if failure == 'timeout': responses[0] = TimeoutError('secret must not be logged')
    if failure == 'large_response': responses[0] = reply(404, raw=b'x'*65537)
    wire = Transport(responses)
    wire.bad_source = failure == 'source'
    snapshots = []
    def no_ping(*args, **kwargs):
        pytest.fail('No ICMP allowed after failed HTTP')
    with pytest.raises(ValueError):
        m.execute(m.make_plan('S10', 'offline-test'), lambda x: snapshots.append(json.dumps(x)),
                  connection_factory=wire.connection, ping=no_ping)
    assert len(wire.calls) <= 2
    assert not json.loads(snapshots[-1])['complete']
    assert all('secret must not' not in s for s in snapshots)


@pytest.mark.parametrize('target', ['https://10.250.0.2:5000', 'http://example.com', 'http://u:p@10.250.0.2:5000', 'http://10.250.0.2:5000/path'])
def test_s8s10_rejects_unapproved_origin(target):
    m = load('tools/s8s10_input.py')
    with pytest.raises(ValueError):
        m.make_plan('S8', 'offline-test', target)


def test_s8s10_default_plan_and_preserved_output(tmp_path, monkeypatch):
    m = load('tools/s8s10_input.py')
    out = tmp_path / 'plan.json'
    monkeypatch.setattr('sys.argv', ['input', '--case', 'S8', '--run-id', 'offline-test', '--out', str(out)])
    m.main()
    assert json.loads(out.read_text())['scope'] == 'offline_plan'
    before = out.read_bytes()
    with pytest.raises(SystemExit): m.main()
    assert out.read_bytes() == before


def test_recorded_source_hashes():
    manifest = json.loads((ROOT/'lab/input-tools-provenance.json').read_text())
    for item in manifest['files']:
        assert hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest() == item['sha256']
