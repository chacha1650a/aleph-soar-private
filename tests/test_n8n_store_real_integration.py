"""Merged D flags and list queries through generated nodes and C's isolated API."""
from urllib.parse import parse_qs, urlsplit

import pytest

from ticket_store import db
from ticket_store.app import create_n8n_app
from tests.test_n8n_workflow_integration import ACTION, CHECK, IP, context, evaluate, evaluate_steps

KEY = 'synthetic-integration-key'


@pytest.mark.parametrize('flags,expected', [
    ({}, {'dry_run': True, 'store_real': False}),
    ({'dry_run': False}, {'dry_run': False, 'store_real': False}),
    ({'store_real': True}, {'dry_run': True, 'store_real': True}),
    ({'dry_run': False, 'store_real': True}, {'dry_run': False, 'store_real': True}),
    ({'dry_run': 'false', 'store_real': 'true'}, {'dry_run': True, 'store_real': False}),
    ({'dry_run': 0, 'store_real': 1}, {'dry_run': True, 'store_real': False}),
])
def test_s1_entry_requires_literal_run_and_storage_switches(flags, expected):
    body = {'event_id': 'synthetic-s1-switch', 'asset_id': 'haedam-portal',
            'src_ip': IP, 'username': 'synthetic-user', **flags}
    result = evaluate('haedam-30-s1-main.json', '입력 검증·설정', {'body': body})
    assert result['http_calls'] == 0
    assert result['output']['proceed'] is True
    assert result['output']['ctx']['cfg'] == expected


def test_s1_real_switches_never_bypass_the_normal_source_guard():
    body = {'event_id': 'synthetic-s1-normal-guard', 'asset_id': 'haedam-portal',
            'src_ip': '203.0.113.12', 'username': 'synthetic-user',
            'dry_run': False, 'store_real': True}
    result = evaluate('haedam-30-s1-main.json', '입력 검증·설정', {'body': body})
    assert result['http_calls'] == 0
    assert result['output']['verdict'] == 'protected_source'
    assert 'ctx' not in result['output'] and 'proceed' not in result['output']


@pytest.mark.parametrize('cfg,expected', [
    ({'dry_run': True, 'store_real': True}, True),
    ({'dry_run': False, 'store_real': True}, True),
    ({'dry_run': True, 'store_real': False}, False),
    ({'dry_run': False, 'store_real': False}, False),
    ({'dry_run': False}, True),
    ({'dry_run': True}, False),
    ({'dry_run': False, 'store_real': None}, False),
    ({'dry_run': False, 'store_real': 'true'}, False),
])
def test_storage_selection_is_independent_of_device_mode_and_keeps_legacy_callers(cfg, expected):
    result = evaluate(CHECK, '저장소 요청 만들기', {
        'mode': 'check', 'seat': 'A', 'group_key': 'zz_s1', 'ctx': context(cfg=cfg)})
    assert result['http_calls'] == 0
    assert result['output']['real'] is expected


def request_body(**changes):
    return {'mode': 'record', 'seat': 'A', 'case_id': 'S1', 'group_key': 'zz_s1',
            'stage': 'applied', 'asset_id': 'haedam-portal', 'src_ip': IP,
            'event_ids': ['synthetic-flag-test'], 'idempotency_key': 'synthetic-flag-record',
            'action': {**ACTION, 'result': 'dry_run'},
            'ctx': context(cfg={'dry_run': True, 'store_real': True}), **changes}


@pytest.mark.parametrize('result', ['dry_run', 'skipped'])
def test_store_real_dry_result_creates_only_detected_ticket_in_actual_c_api(tmp_path, result):
    client = create_n8n_app(str(tmp_path / 'tickets.db'), KEY).test_client()
    route = evaluate(CHECK, '저장소 요청 만들기', request_body(action={**ACTION, 'result': result}))['output']
    assert route['method'] == 'POST' and route['body']['stage'] == 'detected'
    assert route['body']['action'] is None and route['idem'].endswith('-dry')
    response = client.post(urlsplit(route['url']).path, json=route['body'],
                           headers={'X-Response-Key': KEY, 'Idempotency-Key': route['idem']})
    assert response.status_code == 201
    assert response.json['status'] == 'open'
    with db.connect(str(tmp_path / 'tickets.db')) as conn:
        ticket = db.get_ticket(conn, response.json['ticket_id'])
        assert ticket['actions'] == []


def test_target_only_query_returns_both_seats_even_for_a_closed_active_claim(tmp_path):
    client = create_n8n_app(str(tmp_path / 'tickets.db'), KEY).test_client()
    headers = {'X-Response-Key': KEY}
    ids = []
    for seat, group in [('A', 'zz_s1'), ('B', IP)]:
        body = request_body(seat=seat, group_key=group, event_ids=['synthetic-' + seat],
                            action={**ACTION, 'result': 'applied'},
                            ctx=context(cfg={'dry_run': False, 'store_real': True}))
        route = evaluate(CHECK, '저장소 요청 만들기', body)['output']
        response = client.post(urlsplit(route['url']).path, json=route['body'],
                               headers={**headers, 'Idempotency-Key': 'synthetic-record-' + seat})
        assert response.status_code == 201
        ids.append(response.json['ticket_id'])
    # Deliberately inconsistent legacy state: a closed ticket still owning a block.
    with db.connect(str(tmp_path / 'tickets.db')) as conn:
        conn.execute("UPDATE tickets SET status = 'closed' WHERE ticket_id = ?", (ids[0],))
        conn.commit()
    route = evaluate(CHECK, '저장소 요청 만들기', {
        'mode': 'check', 'seat': 'D', 'target': IP,
        'ctx': context(cfg={'dry_run': True, 'store_real': True})})['output']
    url = urlsplit(route['url'])
    assert parse_qs(url.query) == {'target': [IP]}
    response = client.get(url.path + '?' + url.query, headers=headers)
    assert response.status_code == 200
    mapped = evaluate(CHECK, '응답 변환 1', {'statusCode': 200, 'body': response.json},
                      prior={'저장소 요청 만들기': route})['output']
    assert mapped['ok'] is True
    assert {t['ticket_id'] for t in mapped['tickets']} == set(ids)
    assert {t['seat'] for t in mapped['tickets']} == {'A', 'B'}
    assert next(t for t in mapped['tickets'] if t['seat'] == 'A')['status'] == 'closed'


@pytest.mark.parametrize('body', [
    {'ok': True},
    {'ok': True, 'tickets': None},
    {'ok': True, 'tickets': [{'seat': 'A', 'ticket_id': 'bad', 'status': 'open', 'active_actions': []}]},
    {'ok': True, 'tickets': [{'seat': 'A', 'ticket_id': 'T-20261028-0001', 'status': 'responding',
                             'active_actions': [{**ACTION, 'target': '203.0.113.99'}]}]},
])
def test_bad_target_list_never_becomes_a_successful_empty_lookup(body):
    result = evaluate(CHECK, '응답 변환 1', {'statusCode': 200, 'body': body},
                      prior={'저장소 요청 만들기': {'mode': 'check', 'query_scope': 'target',
                                               'target': IP, 'ctx': context()}})['output']
    assert result['ok'] is False and result['no_action'] is True


def test_placeholder_target_and_group_queries_keep_cross_seat_actions():
    records = []
    for seat in ('A', 'B'):
        records.append(request_body(seat=seat, group_key='shared-test-group',
            idempotency_key='synthetic-placeholder-' + seat, event_ids=['synthetic-' + seat],
            action={**ACTION, 'result': 'dry_run'}, ctx=context(cfg={'dry_run': True, 'store_real': False})))
    query = {'mode': 'check', 'target': IP, 'ctx': context()}
    group = {'mode': 'check', 'group_key': 'shared-test-group', 'ctx': context()}
    results = evaluate_steps([{'file': CHECK, 'node': 'check/record (자리표시 저장소)', 'input': b}
                              for b in records + [query, group]])
    assert all(r['http_calls'] == 0 and 'error' not in r for r in results)
    for result in results[-2:]:
        assert result['output']['ok'] is True
        assert {t['seat'] for t in result['output']['tickets']} == {'A', 'B'}
