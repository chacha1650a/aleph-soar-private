"""Operator mistakes must not discard the original S4 session or send traffic."""
import io
import json
import sys

import pytest

from tests.test_b_input_followup import round_args, setup_round
from tests.test_b_input_tools import load, no_network, reply


def test_mistyped_lock_and_unlock_wait_without_requests_or_losing_session(tmp_path, monkeypatch, capsys):
    m, wire = setup_round(monkeypatch)
    out = tmp_path / 'repeat.json'
    answers = iter([
        ('', 7), ('UNLOCKED', 7), ('PRIVATE-ACCIDENTAL-INPUT', 7), (' locked ', 7),
        ('LOCKED', 13), ('', 13), (' unlocked ', 13),
    ])

    def gate(prompt):
        answer, expected_calls = next(answers)
        assert len(wire.calls) == expected_calls
        saved = json.loads(out.read_text())
        assert saved['operator_gates'][-1]['status'] == 'waiting'
        assert not any('cleanup' in s['phase'] for s in saved['steps'])
        return answer

    result = m.run(out, 'reset', 'TARGET-SECRET', 'NORMAL-SECRET', gate=gate,
                   reset_password=lambda: 'RESET-SECRET', **round_args())
    assert result['complete'] and len(wire.calls) == 16
    assert [g['invalid_entries'] for g in result['operator_gates']] == [3, 2]
    assert all(g['status'] == 'confirmed' and g['finished_kst'] for g in result['operator_gates'])
    assert wire.calls[7][3]['Cookie'] == wire.calls[13][3]['Cookie'] == 'haedam_session=SYNTHETIC-ORIGINAL'
    assert result['automatic_retries'] == result['response_API_calls'] == 0
    combined = out.read_text() + capsys.readouterr().out
    assert not any(s in combined for s in ['PRIVATE-ACCIDENTAL-INPUT', 'TARGET-SECRET', 'NORMAL-SECRET', 'RESET-SECRET', 'SYNTHETIC-'])


def test_boundary_wrong_token_cannot_confirm_no_lock(tmp_path, monkeypatch):
    m, wire = setup_round(monkeypatch, 4)
    answers = iter(['LOCKED', 'UNLOCKED', ' no_lock '])

    def gate(prompt):
        assert len(wire.calls) == 6
        return next(answers)

    result = m.run(tmp_path/'edge.json', 'reset', 'x', 'y', gate=gate,
                   reset_password=lambda: pytest.fail('No boundary reset'), **round_args(4))
    assert result['complete'] and len(wire.calls) == 12
    assert result['operator_gates'][0]['gate'] == 'NO_LOCK'
    assert result['operator_gates'][0]['invalid_entries'] == 2
    assert result['external_no_lock_attested_by_operator']


@pytest.mark.parametrize('stop', [' stop ', EOFError('PRIVATE-EOF'), KeyboardInterrupt('PRIVATE-INTERRUPT')])
@pytest.mark.parametrize('at_unlock', [False, True])
def test_explicit_stop_or_closed_terminal_is_incomplete_and_has_safe_reason(tmp_path, monkeypatch, stop, at_unlock):
    m, wire = setup_round(monkeypatch)
    if not at_unlock:
        wire.responses[7] = reply(data={'logged_out': True})  # Existing one-shot session cleanup only.

    def gate(prompt):
        if at_unlock and 'type LOCKED' in prompt:
            return 'LOCKED'
        assert len(wire.calls) == (13 if at_unlock else 7)
        if isinstance(stop, BaseException):
            raise stop
        return stop

    out = tmp_path/'stopped.json'
    result = m.run(out, 'reset', 'x', 'y', gate=gate,
                   reset_password=lambda: pytest.fail('No new credentials after stop'), **round_args())
    assert not result['complete']
    expected_gate = 'unlocked' if at_unlock else 'locked'
    assert result['error_code'].startswith('operator_gate_' + expected_gate + '_')
    assert result['operator_gates'][-1]['status'] == 'stopped'
    assert result['operator_gates'][-1]['finished_kst']
    assert len(wire.calls) == (13 if at_unlock else 8)
    assert 'old_session_still_revoked' not in result['checks']
    if not at_unlock:
        assert 'old_session_revoked' not in result['checks']
    assert 'PRIVATE-' not in out.read_text()
    assert not any('/response/' in c[1] or '/admin/' in c[1] for c in wire.calls)


@pytest.mark.parametrize('answer', ['', 'locked', 'UNLOCKED'])
def test_preserved_version_reproduces_repeat02_interruption_signature(tmp_path, monkeypatch, answer):
    """Reproduce possible causes, without claiming the operator's original text."""
    _, wire = setup_round(monkeypatch)
    old = load('lab/preserved/20261104/s4_session_round.py')
    monkeypatch.setattr(old, 'INTERVAL', 0)
    # The archived live record ended with this cleanup response after the gate.
    wire.responses[7] = reply(403)
    result = old.run(tmp_path/'old.json', 'reset', 'x', 'y',
                     gate=lambda _: answer, **round_args())
    assert result['checks'] == {'trigger_sequence_completed': True}
    assert result['complete'] is False
    assert result['error_type'] == result['target_cleanup_error_type'] == 'ValueError'
    assert [s['phase'] for s in result['steps']] == [
        'bootstrap', *['trigger_failure'] * 5, 'trigger_success', 'target_failure_cleanup_logout',
    ]
    assert result['steps'][-1]['status'] == 403
    assert len(wire.calls) == 8


def test_real_input_lines_reprompt_and_preserve_original_session(tmp_path, monkeypatch, capsys):
    """Exercise input() line consumption, including Enter and wrong-stage lines."""
    m, wire = setup_round(monkeypatch)
    monkeypatch.setattr(sys, 'stdin', io.StringIO('\nUNLOCKED\nlocked\nLOCKED\nunlocked\n'))
    result = m.run(tmp_path/'stdin.json', 'reset', 'x', 'y', gate=input,
                   reset_password=lambda: 'new', **round_args())
    assert result['complete'] and len(wire.calls) == 16
    assert [g['invalid_entries'] for g in result['operator_gates']] == [2, 1]
    assert [g['status'] for g in result['operator_gates']] == ['confirmed', 'confirmed']
    assert wire.calls[7][3]['Cookie'] == wire.calls[13][3]['Cookie'] == 'haedam_session=SYNTHETIC-ORIGINAL'
    assert capsys.readouterr().out.count('Still waiting. No request sent.') == 3


@pytest.mark.parametrize('stop', ['STOP', EOFError(), KeyboardInterrupt()])
def test_boundary_stop_does_not_claim_no_lock_or_start_normal_checks(tmp_path, monkeypatch, stop):
    m, wire = setup_round(monkeypatch, 4)
    wire.responses[6] = reply(data={'logged_out': True})

    def gate(_):
        assert len(wire.calls) == 6
        if isinstance(stop, BaseException):
            raise stop
        return stop

    result = m.run(tmp_path/'boundary-stop.json', 'reset', 'x', 'y', gate=gate,
                   reset_password=lambda: pytest.fail('No reset'), **round_args(4))
    assert not result['complete'] and len(wire.calls) == 7
    assert result['error_code'].startswith('operator_gate_no_lock_')
    assert result['operator_gates'][0]['status'] == 'stopped'
    assert 'external_no_lock_attested_by_operator' not in result
    assert not any(s['phase'].startswith('normal') for s in result['steps'])
    assert result['steps'][-1]['phase'] == 'target_failure_cleanup_logout'

