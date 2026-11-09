"""Follow-up regression tests: synthetic transports, never lab traffic."""
import json
import subprocess
import pytest
from tests.test_b_input_tools import load, Transport, reply, s4_responses, no_network


def round_args(failures=5):
    return dict(run_id='S4-20261104-REPEAT02', account='zz_s4_repeat02',
                source='203.0.113.18', failure_count=failures)


def setup_round(monkeypatch, failures=5, boundary_user=True):
    m = load('lab/s1s4/s4_session_round.py')
    user = {'username': 'zz_s4_repeat02', 'role': 'staff'}
    if failures == 5:
        responses = s4_responses()
        responses[6] = reply(data={'user': user}, cookie='SYNTHETIC-ORIGINAL')
        responses[14] = reply(data={'user': user}, cookie='SYNTHETIC-NEW')
    else:
        responses = [reply(data={'csrf_token': 'SYNTHETIC-CSRF'}, cookie='SYNTHETIC-ANON'),
                     *[reply(401) for _ in range(4)],
                     reply(data={'user': user}, cookie='SYNTHETIC-ORIGINAL'),
                     reply(data={'user': user if boundary_user else None}),
                     *s4_responses()[9:13], reply(data={'logged_out': True})]
    wire = Transport(responses)
    monkeypatch.setattr(m.http.client, 'HTTPConnection', wire.connection)
    monkeypatch.setattr(m, 'INTERVAL', 0)
    return m, wire


@pytest.mark.parametrize('method', ['reset', 'keep'])
def test_repeat_new_identity_and_same_original_session(tmp_path, monkeypatch, method):
    m, wire = setup_round(monkeypatch)
    out = tmp_path/'repeat.json'
    result = m.run(out, method, 'SYNTHETIC-TARGET', 'SYNTHETIC-NORMAL',
        gate=lambda q: 'LOCKED' if 'type LOCKED' in q else 'UNLOCKED',
        reset_password=lambda: 'SYNTHETIC-RESET', **round_args())
    assert result['complete'] and len(wire.calls) == 16
    assert result['run_id'] == round_args()['run_id'] and result['account'] == 'zz_s4_repeat02'
    assert all(x['source'] == '203.0.113.18' for x in result['steps'] if not x['phase'].startswith('normal'))
    assert all(json.loads(x[2])['username'] == 'zz_s4_repeat02' for x in wire.calls
               if x[1].endswith('/login') and json.loads(x[2])['username'] != 'zz_n1')
    assert wire.calls[7][3]['Cookie'] == wire.calls[13][3]['Cookie'] == 'haedam_session=SYNTHETIC-ORIGINAL'
    assert 'SYNTHETIC-' not in out.read_text()
    assert not result['external_ticket_action_closure_verified']
    before = out.read_bytes()
    with pytest.raises(FileExistsError):
        m.run(out, method, 'x', 'y', **round_args())
    assert out.read_bytes() == before and len(wire.calls) == 16


def test_boundary_four_failures_does_not_wait_for_lock_or_reset(tmp_path, monkeypatch):
    m, wire = setup_round(monkeypatch, 4)
    gates = []
    def gate(prompt):
        gates.append(prompt)
        return 'NO_LOCK'
    result = m.run(tmp_path/'boundary.json', 'reset', 'x', 'y', gate=gate,
        reset_password=lambda: pytest.fail('Boundary must not reset'), **round_args(4))
    assert result['complete'] and len(wire.calls) == 12 and len(gates) == 1
    assert 'observation end' in gates[0]
    assert result['expected_outcome'] == 'no_lock'
    assert result['external_no_lock_attested_by_operator'] is True
    assert result['checks']['boundary_same_session_valid']
    assert sum(x['phase'] == 'trigger_failure' for x in result['steps']) == 4
    assert not any('/response/' in x[1] or '/admin/' in x[1] for x in wire.calls)
    assert all(c.closed for c in wire.connections)


def test_unexpected_boundary_lock_stops_without_new_logins(tmp_path, monkeypatch):
    m, wire = setup_round(monkeypatch, 4, boundary_user=False)
    result = m.run(tmp_path/'boundary.json', 'reset', 'x', 'y', gate=lambda _: 'NO_LOCK', **round_args(4))
    assert not result['complete'] and len(wire.calls) == 7
    assert 'boundary_same_session_valid' not in result['checks']
    assert result['automatic_retries'] == 0


@pytest.mark.parametrize('change', [
    {'run_id': 'S4-20261103-LIVE01'}, {'run_id': '../escape'},
    {'account': 'admin'}, {'account': 'zz_n1'}, {'source': '203.0.113.100'},
    {'source': '203.0.113.1'}, {'source': '203.0.113.10'}, {'source': '203.0.113.12'},
    {'source': '10.250.0.2'}, {'failure_count': 6},
])
def test_invalid_round_rejected_before_evidence_or_io(tmp_path, change):
    m = load('lab/s1s4/s4_session_round.py')
    args = {**round_args(), **change}
    with pytest.raises(ValueError):
        m.run(tmp_path/'invalid.json', 'reset', 'x', 'y', **args)
    assert not (tmp_path/'invalid.json').exists()


def test_new_cli_plan_and_invalid_schedule_no_secrets_or_io(monkeypatch, capsys):
    m = load('lab/s1s4/s4_session_round.py')
    argv = ['s4', '--run-id', 'S4-PLAN', '--account', 'zz_plan', '--source', '203.0.113.17', '--failure-count', '4']
    monkeypatch.setattr(m.sys, 'argv', argv)
    monkeypatch.setattr(m.getpass, 'getpass', lambda _: pytest.fail('No password in plan'))
    assert m.main() == 0 and 'PLAN ONLY' in capsys.readouterr().out
    monkeypatch.setattr(m.sys, 'argv', argv + ['--start-at', '2026-11-04T10:00:00', '--latest-start', '2026-11-04T10:01:00'])
    with pytest.raises(SystemExit): m.main()


@pytest.mark.parametrize('payload', [b'<html>PRIVATE_SECRET</html>', b'[]', b'{"data":null}', b'{"data":{}}'])
def test_csrf_parse_and_shape_failures_have_safe_saved_reason(payload):
    m = load('tools/s8s10_input.py')
    wire = Transport([reply(404), reply(raw=payload)])
    saved = []
    with pytest.raises(ValueError):
        m.execute(m.make_plan('S10', 'TEST'), lambda r: saved.append(json.dumps(r)),
                  connection_factory=wire.connection, ping=lambda *a, **kw: pytest.fail('No ping'))
    result = json.loads(saved[-1])
    assert result['error']['phase'] == 'csrf_bootstrap' and result['finished_at']
    assert not result['complete'] and result['icmp'] is None and len(wire.calls) == 2
    assert 'PRIVATE_SECRET' not in ''.join(saved)


def test_ping_timeout_is_recorded_once_without_stdout():
    m = load('tools/s8s10_input.py')
    wire = Transport([reply(404), reply(data={'csrf_token': 'SYNTHETIC-CSRF'}, cookie='SYNTHETIC-COOKIE'), reply(401)])
    calls, saved = [], []
    def timeout(*args, **kwargs):
        calls.append(args)
        raise subprocess.TimeoutExpired('PRIVATE_COMMAND', 5, output=b'PRIVATE_OUTPUT', stderr=b'PRIVATE_ERROR')
    with pytest.raises(ValueError):
        m.execute(m.make_plan('S10', 'TEST'), lambda r: saved.append(json.dumps(r)),
                  connection_factory=wire.connection, ping=timeout)
    result = json.loads(saved[-1])
    assert result['error'] == {'phase': 'icmp', 'type': 'TimeoutExpired'}
    assert result['icmp']['attempts'] == 1 and result['icmp']['returncode'] is None
    assert not result['complete'] and len(calls) == 1 and len(wire.calls) == 3
    assert 'PRIVATE_' not in ''.join(saved)
