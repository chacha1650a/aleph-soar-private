"""Generated S12 detection/recovery nodes, fake clock and synthetic HTTP only."""
from copy import deepcopy
import json

import pytest

from tests.test_n8n_workflow_integration import evaluate

FILE = 'haedam-20-s12-main.json'
OK = {'statusCode': 200, 'body': {'success': True, 'data': {'status': 'ok'}}}


def config(**changes):
    return {'baseline_ms': 1000, 'baseline_source': 'synthetic-evidence', 'health_timeout_ms': 5000, 'health_interval_ms': 2000,
            'health_k': 3, 'health_url': 'synthetic-only', 'dry_run': True, **changes}


def run(samples=None, node='헬스체크 K회', **changes):
    return evaluate(FILE, node, {'ctx': {'cfg': config(**changes), 'event_id': 'synthetic-s12'}},
                    clock_ms=1793664000000, responses=deepcopy(samples or []))


def response(ms=100, body=None):
    return {'delay_ms': ms, 'response': OK if body is None else body}


def test_slow_valid_200_beyond_3414_is_distinct_from_timeout():
    result = run([response(4200)] * 3, baseline_ms=3414)
    assert result['output']['verdict'] == 'exceeded'
    assert {s['classification'] for s in result['output']['health']['samples']} == {'slow_success'}
    assert all(r['timeout'] == 5000 for r in result['requests'])


@pytest.mark.parametrize('changes,verdict', [
    ({'baseline_ms': None}, 'no_baseline'),
    ({'baseline_ms': 3414, 'health_timeout_ms': 3000}, 'invalid_health_config'),
    ({'baseline_ms': 5000}, 'invalid_health_config'),
    ({'baseline_ms': 'NaN'}, 'invalid_health_config'),
    ({'baseline_ms': True}, 'invalid_health_config'),
    ({'baseline_source': None}, 'invalid_health_config'),
    ({'baseline_ms': -1}, 'invalid_health_config'),
    ({'health_k': 0}, 'invalid_health_config'),
    ({'health_k': 11}, 'invalid_health_config'),
    ({'health_interval_ms': 0}, 'invalid_health_config'),
])
def test_unusable_settings_hold_before_requests(changes, verdict):
    result = run(**changes)
    assert result['http_calls'] == 0
    assert result['output']['verdict'] == verdict


@pytest.mark.parametrize('sample,classification', [
    ({'error': {'code': 'ETIMEDOUT', 'message': 'Authorization Bearer synthetic-secret'}}, 'timeout'),
    ({'error': {'code': 'ECONNREFUSED', 'message': 'synthetic-secret'}}, 'network_error'),
    (response(body={'statusCode': 503, 'body': {}}), 'server_error'),
])
def test_failure_categories_never_copy_raw_errors(sample, classification):
    result = run([sample] * 3)
    assert result['output']['verdict'] == 'exceeded'
    assert {s['classification'] for s in result['output']['health']['samples']} == {classification}
    assert 'synthetic-secret' not in json.dumps(result)


@pytest.mark.parametrize('status,body', [(200, {}), (200, {'success': False}), (401, {}), (403, {}), (302, {})])
def test_status_or_body_contract_failures_are_inconclusive(status, body):
    result = run([response(body={'statusCode': status, 'body': body})] * 3)
    assert result['output']['verdict'] == 'inconclusive'


def test_invalid_json_does_not_become_a_network_outage():
    result = run([{'error': {'name': 'SyntaxError', 'message': 'synthetic-secret'}}] * 3)
    assert result['output']['verdict'] == 'inconclusive'
    assert all(s['classification'] == 'invalid_body' for s in result['output']['health']['samples'])


def test_k_healthy_and_mixed_samples_are_not_both_called_normal():
    assert run([response()] * 3)['output']['verdict'] == 'within_baseline'
    assert run([response(1200), response(), response(1200)])['output']['verdict'] == 'inconclusive'


def test_detection_and_recovery_share_latency_boundary_and_contract():
    healthy = run([response(1000)] * 3)
    recovery = run([response(1000)] * 3, node='회복 확인', dry_run=False)
    assert healthy['output']['verdict'] == 'within_baseline'
    assert recovery['output']['recovered'] is True
    assert recovery['output']['effect_verified'] is None
    assert recovery['output']['noop'] is True
    assert recovery['output']['ctx']['recovery']['normal_user_path_verified'] is None


def test_recovery_streak_resets_and_observation_deadline_is_bounded():
    samples = [response(), response(1200), response(), response(), response()]
    result = run(samples, node='회복 확인', recover_timeout_ms=30000)
    assert result['output']['recovered'] is True and result['http_calls'] == 5
    held = run(node='회복 확인', recover_timeout_ms=1000)
    assert held['http_calls'] == 0 and held['output']['recovered'] is False


def test_measured_baseline_default_and_body_overrides_remain_dry_run_only():
    payload = {'event_id': 'synthetic-s12', 'asset_id': 'haedam-portal', 'src_ip': '203.0.113.41'}
    ctx = evaluate(FILE, '입력 검증·설정', {'body': payload})['output']['ctx']
    assert ctx['cfg']['baseline_ms'] == 2000 and ctx['cfg']['baseline_source'] == 'S12-20261103-D-HEALTH-BASELINE01'
    assert ctx['cfg']['baseline_ms'] < ctx['cfg']['health_timeout_ms']
    synthetic = evaluate(FILE, '입력 검증·설정', {'body': {**payload, 'test_baseline_ms': 1000}})['output']['ctx']
    assert synthetic['cfg']['baseline_source'] == 'synthetic_override'
    assert synthetic['cfg']['dry_run'] is True
