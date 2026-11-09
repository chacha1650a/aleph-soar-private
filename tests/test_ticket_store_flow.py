from ticket_store import db
import pytest
from ticket_store import samples
from ticket_store.app import create_dashboard_app

@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "tickets.db")
    conn = db.connect(path)
    samples.load_samples(conn)
    conn.close()
    return path

def client_for(path):
    return create_dashboard_app(path, "http://127.0.0.1:8089").test_client()


def test_case_board_keeps_samples_hidden_and_labels_unknown(db_path):
    client = client_for(db_path)
    page = client.get('/cases').get_data(as_text=True)
    assert 'T-20261024-9001' not in page
    assert '비교 자료 없음' in page
    page = client.get('/cases?sample=1').get_data(as_text=True)
    assert 'T-20261024-9006' in page and '샘플' in page


def test_work_queue_excludes_closed_and_identifies_effect_wait(db_path):
    client = client_for(db_path)
    page = client.get('/work?sample=1').get_data(as_text=True)
    assert '효과 확인 대기' in page and 'T-20261024-9002' in page
    assert 'T-20261024-9005' not in page
    assert 'T-20261024-9002' not in client.get('/work').get_data(as_text=True)


def test_detail_starts_with_ticket_creation_and_missing_times(db_path):
    client = client_for(db_path)
    page = client.get('/tickets/T-20261024-9002').get_data(as_text=True)
    assert '대응 흐름' in page and '티켓 생성' in page and '미측정' in page

def test_failed_release_keeps_prior_active_action(db_path):
    conn = db.connect(db_path)
    row = conn.execute("SELECT * FROM actions WHERE ticket_id=?", ('T-20261024-9002',)).fetchone()
    action = {field: row[field] for field in db.ACTION_FIELDS}
    action.update(action='unblock', result='failed', applied_verified=False)
    db.insert_action(conn, 'T-20261024-9002', action, 'failed-unblock-unique', row['recorded_at'])
    conn.commit()
    item = next(x for x in db.dashboard_work(conn, include_sample=True)['items'] if x['ticket_id'] == 'T-20261024-9002')
    assert item['failed'] and item['restore_wait'] and item['effect_wait']
    assert db.dashboard_has_active(conn, 'T-20261024-9002')
    conn.close()

def test_sample_and_live_counts_are_separate(db_path):
    conn = db.connect(db_path)
    conn.execute("UPDATE tickets SET data_origin='live' WHERE ticket_id='T-20261024-9001'")
    conn.commit()
    board = db.dashboard_cases(conn, seat='C', include_sample=True)
    counts = {source['origin']: source['count'] for source in board[0]['sources']}
    assert counts == {'live': 1, 'sample': 1}
    conn.close()


def test_dashboard_history_is_bounded_and_latest_independent(db_path):
    conn = db.connect(db_path)
    row = conn.execute("SELECT * FROM actions WHERE ticket_id=?", ('T-20261024-9002',)).fetchone()
    action = {field: row[field] for field in db.ACTION_FIELDS}
    for i in range(210):
        action['result'] = 'failed' if i == 209 else 'applied'
        db.insert_action(conn, 'T-20261024-9002', action, 'many-action-%04d' % i, row['recorded_at'])
    conn.commit()
    first = db.dashboard_ticket(conn, 'T-20261024-9002', page=1)
    second = db.dashboard_ticket(conn, 'T-20261024-9002', page=2)
    assert len(first['actions']) == 50 and first['more_actions']
    assert first['last_result'] == second['last_result'] == 'failed'
    assert len(db.dashboard_ticket(conn, 'T-20261024-9002', limit=999)['actions']) == 200
    conn.close()


def test_related_check_does_not_cross_data_origins(db_path):
    conn = db.connect(db_path)
    row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", ('T-20261024-9002',)).fetchone()
    data = dict(row)
    data.update(ticket_id='T-20261024-9999', seat='B', data_origin='live')
    columns = ','.join(data)
    conn.execute('INSERT INTO tickets (' + columns + ') VALUES (' + ','.join('?' for _ in data) + ')', tuple(data.values()))
    original = conn.execute("SELECT * FROM actions WHERE ticket_id=?", ('T-20261024-9002',)).fetchone()
    action = {field: original[field] for field in db.ACTION_FIELDS}
    db.insert_action(conn, 'T-20261024-9999', action, 'other-origin-active', original['recorded_at'])
    conn.commit()
    work = db.dashboard_work(conn, include_sample=True)['items']
    assert not next(x for x in work if x['ticket_id']=='T-20261024-9002')['related']
    conn.close()

def test_related_alert_includes_closed_ticket_with_active_record(db_path):
    conn = db.connect(db_path)
    row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", ('T-20261024-9002',)).fetchone()
    data = dict(row)
    data.update(ticket_id='T-20261024-9998', seat='B', status='closed', close_note='old record')
    conn.execute('INSERT INTO tickets (' + ','.join(data) + ') VALUES (' + ','.join('?' for _ in data) + ')', tuple(data.values()))
    original = conn.execute("SELECT * FROM actions WHERE ticket_id=?", ('T-20261024-9002',)).fetchone()
    action = {field: original[field] for field in db.ACTION_FIELDS}
    db.insert_action(conn, 'T-20261024-9998', action, 'closed-other-active', original['recorded_at'])
    conn.commit()
    item = next(x for x in db.dashboard_work(conn, include_sample=True)['items'] if x['ticket_id']=='T-20261024-9002')
    assert item['related']
    conn.close()


def test_index_renders_case_board_preview_once(db_path):
    page = client_for(db_path).get('/?sample=1').get_data(as_text=True)
    assert page.count('id="case-board-title"') == 1


def test_case_board_links_registered_s12_comparison_within_origin(db_path, tmp_path):
    import json, shutil
    from pathlib import Path
    from ticket_store import s12_measurements
    examples = Path(__file__).resolve().parents[1] / 'contracts/s12-examples'
    for name in ('before.sample.csv', 'after.sample.csv'):
        shutil.copy(examples / name, tmp_path / name)
    meta = json.loads((examples / 'comparison.sample.json').read_text(encoding='utf-8'))
    conn = db.connect(db_path)
    s12_measurements.import_comparison(conn, meta, tmp_path / 'before.sample.csv', tmp_path / 'after.sample.csv')
    client = client_for(db_path)
    hidden = client.get('/cases?seat=D').get_data(as_text=True)
    assert '비교 자료 없음' in hidden and '/s12' not in hidden.split('case-compare')[1]
    shown = client.get('/cases?seat=D&sample=1').get_data(as_text=True)
    assert '샘플 비교 1건' in shown and '/s12?sample=1' in shown and '비교 자료 없음' not in shown
    other = client.get('/cases?seat=A&sample=1').get_data(as_text=True)
    assert '비교 자료 없음' in other and '비교 1건' not in other
    conn.execute("UPDATE tickets SET data_origin='live' WHERE ticket_id=?", (meta['ticket_id'],))
    conn.execute("UPDATE s12_comparisons SET data_origin='live'")
    conn.commit()
    conn.close()
    live = client.get('/cases?seat=D').get_data(as_text=True)
    assert '실제 비교 1건' in live and '/s12?sample=0' in live
