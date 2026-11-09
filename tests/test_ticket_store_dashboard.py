"""Security dashboard screens and close API (design section 6-7, items 1-8; 9 is a deployment test)."""
from datetime import datetime, timedelta
import re
import sqlite3

import pytest

from ticket_store import db, samples
from ticket_store.app import create_dashboard_app
from ticket_store.dashboard import KST

ORIGIN = "http://127.0.0.1:8089"


@pytest.fixture
def empty_path(tmp_path):
    return str(tmp_path / "tickets.db")


@pytest.fixture
def db_path(empty_path):
    conn = db.connect(empty_path)
    samples.load_samples(conn)
    conn.close()
    return empty_path


def client_for(path):
    return create_dashboard_app(path, ORIGIN).test_client()


def page(client, url):
    response = client.get(url)
    assert response.status_code == 200, response.data
    return response.get_data(as_text=True)


def token_of(html):
    return re.search(r'<meta name="dashboard-token" content="([^"]+)">', html).group(1)


def close(client, ticket_id, note="확인 끝", origin=ORIGIN, token=None):
    if token is None:
        token = token_of(page(client, "/"))
    headers = {"X-Dashboard-Token": token}
    if origin:
        headers["Origin"] = origin
    return client.post(f"/api/v1/tickets/{ticket_id}/close", json={"note": note}, headers=headers)


def set_last_record(path, value):
    conn = db.connect(path)
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_record_at', ?)", (value,))
    conn.close()


# 1. no tickets
def test_empty_store_shows_guide_without_error(empty_path):
    html = page(client_for(empty_path), "/")
    assert "아직 티켓이 없습니다" in html and "수신 기록 없음" in html
    assert 'class="conn conn-none"' in html
    assert '<table class="tickets">' not in html


# 2. sample tickets only
def test_samples_only_badge_and_hidden_by_default(db_path):
    client = client_for(db_path)
    html = page(client, "/")
    assert "샘플 데이터" in html and "conn-sample" in html
    assert "T-20261024-9001" not in html
    assert "조건에 맞는 티켓이 없습니다" in html and "샘플 포함" in html
    html = page(client, "/?sample=1")
    assert "T-20261024-9001" in html and html.count('class="flag flag-sample">샘플<') == 5


# 3. five statuses
def test_status_badges_have_text_and_closed_is_hidden_by_default(db_path):
    client = client_for(db_path)
    html = page(client, "/?sample=1&status=all")
    for status, label in [("open", "열림"), ("responding", "대응 중"), ("verified", "효과 확인"),
                          ("restored", "원복"), ("closed", "종료")]:
        assert f'<span class="badge st-{status}">{label}</span>' in html
    assert "T-20261024-9005" in html
    assert "T-20261024-9005" not in page(client, "/?sample=1")
    only_open = page(client, "/?sample=1&status=open")
    assert "T-20261024-9003" in only_open and "T-20261024-9001" not in only_open
    seat_c = page(client, "/?sample=1&seat=C")
    assert "T-20261024-9001" in seat_c and "T-20261024-9002" not in seat_c


@pytest.mark.parametrize("day, closed_count", [(24, "1"), (25, "0")])
def test_summary_counts_and_mttd_mttr(db_path, monkeypatch, day, closed_count):
    monkeypatch.setattr("ticket_store.dashboard.now_kst", lambda: datetime(2026, 10, day, 16, tzinfo=KST))
    html = page(client_for(db_path), "/?sample=1")
    summary = html.split('<ul class="summary">')[1].split("</ul>")[0]
    counts = re.findall(r'st-(\w+)">[^<]+</span> <strong>(\d+)</strong>', summary)
    assert counts == [("open", "1"), ("responding", "2"), ("verified", "1"), ("restored", "1"), ("closed", "1")]
    assert f"오늘 {closed_count}건" in summary
    assert "8초" in html and "42초" in html


# 4. failed response line
def test_failed_action_is_marked_but_status_stays(db_path):
    client = client_for(db_path)
    html = page(client, "/?sample=1")
    row = html.split('data-href="/tickets/T-20261024-9006"')[1].split("</tr>")[0]
    assert '<span class="badge st-responding">대응 중</span>' in row and "대응 실패" in row
    other = html.split('data-href="/tickets/T-20261024-9002"')[1].split("</tr>")[0]
    assert "대응 실패" not in other
    detail = page(client, "/tickets/T-20261024-9006")
    assert "대응 실패" in detail and '<span class="badge st-responding">대응 중</span>' in detail


# 5. store unavailable during refresh
def test_store_failure_keeps_page_and_fragment_reports_error(db_path):
    app = create_dashboard_app(db_path, ORIGIN)
    client = app.test_client()
    assert "T-20261024-9001" in page(client, "/_list?sample=1")

    def broken():
        raise sqlite3.OperationalError("unable to open database file")
    app.extensions["ticket_store_conn"] = broken
    html = page(client, "/")
    assert '<p id="refresh-warning" class="warning">' in html and "갱신 실패" in html
    response = client.get("/_list?sample=1")
    assert response.status_code == 503 and response.get_json()["error"]["code"] == "SERVER_ERROR"
    js = client.get("/static/dashboard.js").get_data(as_text=True)
    assert "warning.hidden = false" in js and 'fetch("/_list"' in js


# 6. close verified / responding
def test_close_verified_and_reject_responding(db_path):
    client = client_for(db_path)
    response = close(client, "T-20261024-9004", note="  S4 원복 확인 끝  ")
    body = response.get_json()
    assert response.status_code == 200 and body["ok"]
    assert body["ticket"]["status"] == "closed" and body["ticket"]["close_note"] == "S4 원복 확인 끝"
    detail = page(client, "/tickets/T-20261024-9004")
    assert "닫힌 티켓입니다" in detail and "S4 원복 확인 끝" in detail
    assert 'id="close-form"' not in detail

    # verified but the quarantine is not released: no close button, 409 with its own reason
    held = page(client, "/tickets/T-20261024-9001")
    assert 'id="close-form"' not in held   # the explanation text for this case is added in B's template (#67)
    response = close(client, "T-20261024-9001")
    assert response.status_code == 409 and response.get_json()["error"]["code"] == "INVALID_TRANSITION"
    assert "not released" in response.get_json()["error"]["message"]

    responding = page(client, "/tickets/T-20261024-9002")
    assert 'id="close-form"' not in responding and "닫을 수 없습니다" in responding
    response = close(client, "T-20261024-9002")
    assert response.status_code == 409
    assert response.get_json() == {"ok": False, "error": {"code": "INVALID_TRANSITION",
                                   "message": "only verified or restored tickets can be closed (now responding)"}}


def test_close_rejects_bad_note_and_unknown_ticket(db_path):
    client = client_for(db_path)
    token = token_of(page(client, "/"))
    assert close(client, "T-20261024-9001", note="", token=token).status_code == 400
    assert close(client, "T-20261024-9001", note="가" * 201, token=token).status_code == 400
    missing = close(client, "T-20261024-0000", token=token)
    assert missing.status_code == 404 and missing.get_json()["error"]["code"] == "NOT_FOUND"


# 7. other origin
def test_close_needs_dashboard_origin_and_token(db_path):
    client = client_for(db_path)
    token = token_of(page(client, "/"))
    for origin, sent_token in [("http://evil.example", token), ("http://10.250.0.3:8089", token),
                               (None, token), (ORIGIN, ""), (ORIGIN, "wrong-token")]:
        response = close(client, "T-20261024-9001", origin=origin, token=sent_token)
        assert response.status_code == 403 and response.get_json()["error"]["code"] == "FORBIDDEN"
    conn = db.connect(db_path)
    assert db.get_ticket(conn, "T-20261024-9001")["status"] == "verified"


# 8. narrow screen (layout itself checked in a real browser at 375px)
def test_narrow_screen_rules_and_security_headers(db_path):
    client = client_for(db_path)
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Frame-Options"] == "DENY"
    css = client.get("/static/dashboard.css").get_data(as_text=True)
    assert "@media (max-width: 700px)" in css and "table.tickets td.extra { display: none; }" in css
    assert "<script>" not in html and "https://" not in html


def test_detail_timeline_actions_and_events(db_path):
    client = client_for(db_path)
    html = page(client, "/tickets/T-20261024-9001")
    assert "계정 없음 사건" in html
    assert '<time title="2026-10-24T14:05:20+09:00">2026-10-24 14:05:20</time>' in html
    assert re.search(r"<span>MTTD</span> 8초", html) and re.search(r"<span>MTTR</span> 42초", html)
    assert html.count("아직 없음") == 2
    assert 'data-copy="sample-graylog-s7-event-01"' in html and "_id:sample-graylog-s7-event-01" in html
    assert "graylog" not in "".join(re.findall(r'href="([^"]+)"', html)).lower()
    restored = page(client, "/tickets/T-20261024-9004")
    assert re.search(r"<span>효과 확인→원복 기록</span> \d", restored)
    assert client.get("/tickets/T-20261024-0000").status_code == 404


def test_duplicate_action_rows_are_dimmed(db_path):
    conn = db.connect(db_path)
    ticket = db.get_ticket(conn, "T-20261024-9002")
    with conn:
        db.insert_action(conn, ticket["ticket_id"], ticket["actions"][0], "sample-5678-applied-dup",
                         "2026-10-24T15:00:05+09:00", duplicate=True)
    conn.close()
    html = page(client_for(db_path), "/tickets/T-20261024-9002")
    assert html.count('<tr class="dup">') == 1 and '<span class="flag">중복</span>' in html


def test_connection_badge_live_and_quiet(db_path):
    client = client_for(db_path)
    now = datetime.now(KST)
    set_last_record(db_path, (now - timedelta(minutes=1)).isoformat(timespec="seconds"))
    assert "실제 연결 · 마지막 수신" in page(client, "/")
    set_last_record(db_path, (now - timedelta(minutes=25)).isoformat(timespec="seconds"))
    assert "n8n 수신 없음 25분" in page(client, "/")


def test_filtered_queue_discloses_global_summary_and_synthetic_scope(db_path):
    html = page(client_for(db_path), "/?sample=1&seat=C")
    assert 'aria-label="티켓 필터"' in html
    assert "자리·케이스 필터와 별도 집계" in html
    assert "샘플 포함 조회" in html and "합성 예시가 현황과 목록에 포함" in html
    assert html.count('class="row"') == 2
    assert "T-20261024-9003" not in html
    assert 'id="refresh-now"' in html and 'href="#main-content"' in html


def test_action_checks_distinguish_unknown_and_false_without_changing_close_policy(db_path):
    client = client_for(db_path)
    pending = page(client, "/tickets/T-20261024-9002")
    assert '<span class="verification unknown">미확인</span>' in pending
    assert 'id="close-form"' not in pending
    failed = page(client, "/tickets/T-20261024-9006")
    assert '<span class="verification denied">아니오</span>' in failed
    assert "실제 차단 해제·원복은 별도로 확인" in failed
    assert 'aria-label="대응 기록 표"' in failed


def test_new_dashboard_header_and_refreshed_fragment_escape_stored_titles(db_path):
    from contextlib import closing
    title = '<img src=x onerror="alert(1)">'
    with closing(db.connect(db_path)) as conn:
        with conn:
            conn.execute("UPDATE tickets SET title = ? WHERE ticket_id = ?", (title, "T-20261024-9001"))
    client = client_for(db_path)
    for route in ("/?sample=1", "/_list?sample=1", "/tickets/T-20261024-9001"):
        html = page(client, route)
        assert title not in html
        assert "&lt;img src=x onerror=" in html


def test_overview_links_reset_queue_filters_and_preserve_sample_scope(db_path):
    from html import unescape
    html = page(client_for(db_path), '/?sample=1&seat=C&case_id=S7')
    overview = html.split('<ul class="summary">')[1].split('</ul>')[0]
    links = re.findall(r'href="([^"]+)"', overview)
    assert len(links) == 5
    for link in links:
        link = unescape(link)
        assert 'sample=1' in link and 'seat=' not in link and 'case_id=' not in link
        result = page(client_for(db_path), link)
        assert 'aria-current="page"' in result
        assert 'id="filters"' in result
    assert '종료 제외 · 저장소 전체' in html
    assert 'href="/?case_id=S7&amp;sample=1#incident-list-title"' in html
    assert 'href="/?seat=C&amp;sample=1#incident-list-title"' in html
    assert 'id="filters"' in page(client_for(db_path), '/_list?sample=1&seat=C')


def test_distributions_use_all_open_records_not_capped_or_filtered_queue(db_path):
    from copy import deepcopy
    from ticket_store.dashboard import list_view
    conn = db.connect(db_path)
    template = samples.sample_tickets()[0]
    with conn:
        for index in range(205):
            ticket = deepcopy(template)
            ticket.update(ticket_id=f'T-distribution-{index}', group_key=f'unique-{index}',
                          seat='A', case_id='S4', status='open')
            db.insert_ticket(conn, ticket)
    conn.close()
    app = create_dashboard_app(db_path, ORIGIN)
    with app.app_context():
        view = list_view({'sample': '1', 'status': 'all'})
        assert len(view['tickets']) == 200
        for chart in view['distributions']:
            assert sum(row['count'] for row in chart['rows']) == 210
        filtered = list_view({'sample': '1', 'seat': 'C', 'status': 'verified'})
        assert len(filtered['tickets']) == 1
        assert filtered['distributions'] == view['distributions']
        live_only = list_view({})
        assert all(row['count'] == 0 for chart in live_only['distributions'] for row in chart['rows'])
