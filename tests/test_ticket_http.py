"""Real loopback sockets, synthetic responses; never school addresses or target APIs."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from tools.ticket_http import TicketHTTP

KEY = "synthetic-http-key-0001"
RESOURCE = {"asset_id": "haedam-portal", "via": "portal", "action": "block", "target": "203.0.113.11"}
EXPECTED = {"seat": "D", "group_key": "asset:dir/a b+한글?x=1", "bot": "112", "resource": RESOURCE,
            "owner_ticket_id": "T-20261024-0001"}


@contextmanager
def server(*, body=None, raw=None, status=200, content_type="application/json", delay=0, incomplete=False):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            requests.append({"method": self.command, "url": self.path, "key": self.headers.get("X-Response-Key")})
            if delay:
                time.sleep(delay)
            payload = raw if raw is not None else json.dumps(body).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload) + (10 if incomplete else 0)))
                if status == 302:
                    self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/elsewhere")
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", requests
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=2)


def test_actual_get_encoding_key_and_captured_query():
    body = {"ok": True, "exists": False, "ticket_id": None, "status": None, "applied_actions": []}
    with server(body=body) as (url, requests):
        result = TicketHTTP(url, KEY).apply(EXPECTED)
    assert result["observation"]["body"] == body
    assert result["observation"]["status"] == 200
    assert result["observation"]["transport_error"] is False
    sent = urlsplit(requests[0]["url"])
    assert sent.path == "/api/v1/tickets/open"
    assert parse_qs(sent.query) == {"seat": ["D"], "group_key": [EXPECTED["group_key"]]}
    assert requests[0]["key"] == KEY and requests[0]["method"] == "GET"
    assert KEY not in json.dumps(result)
    assert len(requests) == 1


def test_active_is_scoped_by_resource_instead_of_seat_or_group():
    with server(body={"ok": True, "resource": RESOURCE, "tickets": []}) as (url, requests):
        result = TicketHTTP(url, KEY).release(EXPECTED)
    assert result["observation"]["query"] == RESOURCE
    assert parse_qs(urlsplit(requests[0]["url"]).query) == {k: [v] for k, v in RESOURCE.items()}
    assert "/active?" in requests[0]["url"]


@pytest.mark.parametrize("status", [401, 404, 500, 503])
def test_http_errors_preserve_status_and_error_body_without_retry(status):
    body = {"ok": False, "error": {"code": "SERVER_ERROR", "message": "synthetic error"}}
    with server(body=body, status=status) as (url, requests):
        observation = TicketHTTP(url, KEY).release(EXPECTED)["observation"]
    assert observation["status"] == status and observation["body"] == body
    assert len(requests) == 1


@pytest.mark.parametrize("raw, content_type, error", [
    (b'<html>error</html>', "text/html", "non_json_response"),
    (b'{', "application/json", "invalid_json_response"),
    (b'{"ok":false,"ok":true}', "application/json", "invalid_json_response"),
    (b'{"count":NaN}', "application/json", "invalid_json_response"),
    (b'[]', "application/json", "invalid_json_response"),
    (b'\xff', "application/json", "invalid_json_response"),
    (b'{"text":"' + b'x' * 65536 + b'"}', "application/json", "response_too_large"),
], ids=["html", "broken", "duplicate-key", "nan", "array", "bad-utf8", "oversized"])
def test_unusable_response_does_not_invent_a_zero(raw, content_type, error):
    with server(raw=raw, content_type=content_type) as (url, requests):
        observation = TicketHTTP(url, KEY).release(EXPECTED)["observation"]
    assert observation["error"] == error and "body" not in observation
    assert observation["status"] == 200 and len(requests) == 1


def test_redirect_is_not_followed_or_forwarded_the_key():
    with server(raw=b'', status=302) as (url, requests):
        observation = TicketHTTP(url, KEY).release(EXPECTED)["observation"]
    assert observation["error"] == "redirect_blocked" and observation["status"] == 302
    assert len(requests) == 1


@pytest.mark.parametrize("kwargs", [{"delay": .15}, {"incomplete": True}])
def test_transport_timeout_or_truncated_body_is_unknown_not_zero(kwargs):
    with server(body={"ok": True}, **kwargs) as (url, requests):
        observation = TicketHTTP(url, KEY, timeout=.03).release(EXPECTED)["observation"]
    assert observation["transport_error"] is True and observation["status"] is None
    assert "body" not in observation and len(requests) == 1


@pytest.mark.parametrize("url", ["http://10.250.0.3:8088", "http://localhost:8088", "http://example.com:80",
    "https://127.0.0.1:443", "http://127.0.0.1:1/path", "http://user:pass@127.0.0.1:80", "http://127.0.0.1:0"])
def test_home_adapter_rejects_nonliteral_loopback_or_ambiguous_urls(url):
    with pytest.raises(ValueError):
        TicketHTTP(url, KEY)


def test_invalid_scope_stops_before_network():
    client = TicketHTTP("http://127.0.0.1:1", KEY)
    with pytest.raises(ValueError):
        client.release({"resource": {**RESOURCE, "seat": "D"}})
    with pytest.raises(ValueError):
        client.apply({"seat": "E", "group_key": "x"})


def test_http_receipts_reach_exported_js_as_hold_or_zero_distinctly():
    if not __import__("shutil").which("node"):
        pytest.skip("Node.js required for generated JS execution")
    from tools.check_ticket_guard import evaluate
    observations = []
    for status, body in [(200, {"ok": True, "resource": RESOURCE, "tickets": []}), (500, {"ok": False})]:
        with server(status=status, body=body) as (url, requests):
            observations.append(TicketHTTP(url, KEY).release(EXPECTED))
    answers = evaluate(observations)
    assert [a["reason"] for a in answers] == ["no_recorded_claims", "store_query_failed"]
    assert all(a["decision"] == "hold" and a["allow_target_call"] is False for a in answers)
