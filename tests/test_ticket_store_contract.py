"""Every JSON response the ticket store actually sends must match contracts/ticket-response.schema.json."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest
from referencing import Registry, Resource

from ticket_store import core, db, samples
from ticket_store.app import create_dashboard_app, create_n8n_app

ROOT = Path(__file__).resolve().parents[1]
KEY = "test-key-not-a-secret-0001"
ORIGIN = "http://127.0.0.1:8089"
SCHEMAS = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "contracts").glob("*.schema.json")]
RESPONSE = Draft202012Validator(
    json.loads((ROOT / "contracts/ticket-response.schema.json").read_text(encoding="utf-8")),
    registry=Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in SCHEMAS),
    format_checker=FormatChecker(formats=["date-time", "ipv4", "ipv6"]))


@pytest.fixture
def clients(tmp_path):
    path = str(tmp_path / "tickets.db")
    samples.load_samples(db.connect(path))
    dashboard_app = create_dashboard_app(path, ORIGIN)
    return create_n8n_app(path, KEY).test_client(), dashboard_app.test_client(), dashboard_app.config["DASHBOARD_TOKEN"]


def conforms(response, status, code=None):
    body = response.get_json()
    assert response.status_code == status, body
    RESPONSE.validate(body)
    if code:
        assert body["error"]["code"] == code
    return body


def close(client, ticket_id, token, origin=ORIGIN, note="확인 끝"):
    return client.post(f"/api/v1/tickets/{ticket_id}/close", json={"note": note},
                       headers={"Origin": origin, "X-Dashboard-Token": token})


def test_dashboard_list_detail_and_close_follow_the_contract(clients):
    _, dashboard, token = clients
    assert conforms(dashboard.get("/api/v1/tickets"), 200)["count"] == 0
    listing = conforms(dashboard.get("/api/v1/tickets?sample=1&status=open,responding,verified,restored,closed"), 200)
    assert listing["count"] == 6 and set(listing["counts"]) == set(db.STATUSES)
    conforms(dashboard.get("/api/v1/tickets/T-20261024-9006"), 200)
    conforms(dashboard.get("/api/v1/tickets/T-20261024-0000"), 404, "NOT_FOUND")
    conforms(dashboard.get("/api/v1/tickets?status=contained"), 400, "VALIDATION_ERROR")
    conforms(dashboard.get("/api/v1/tickets?limit=x"), 400, "VALIDATION_ERROR")

    conforms(close(dashboard, "T-20261024-9004", token, origin="http://evil.example"), 403, "FORBIDDEN")
    conforms(close(dashboard, "T-20261024-9004", "wrong-token"), 403, "FORBIDDEN")
    conforms(close(dashboard, "T-20261024-9004", token, note=""), 400, "VALIDATION_ERROR")
    conforms(close(dashboard, "T-20261024-9002", token), 409, "INVALID_TRANSITION")
    conforms(close(dashboard, "T-20261024-0000", token), 404, "NOT_FOUND")
    conforms(close(dashboard, "T-20261024-9001", token), 409, "INVALID_TRANSITION")   # verified, block not released yet
    closed = conforms(close(dashboard, "T-20261024-9004", token), 200)
    assert closed["ticket"]["status"] == "closed" and closed["ticket"]["close_note"] == "확인 끝"


def test_n8n_errors_and_unexpected_failures_keep_the_ok_false_shape(clients, monkeypatch):
    n8n, _, _ = clients
    headers = {"X-Response-Key": KEY, "Idempotency-Key": "exec-1-applied"}
    body = json.loads((ROOT / "contracts/ticket-examples/record-s12-applied.json").read_text(encoding="utf-8"))
    conforms(n8n.post("/api/v1/tickets/record", json=body, headers={**headers, "X-Response-Key": "x"}), 401, "UNAUTHORIZED")
    conforms(n8n.get("/api/v1/tickets/open?group_key=", headers=headers), 400, "VALIDATION_ERROR")
    conforms(n8n.get("/api/v1/tickets/open?group_key=x&seat=E", headers=headers), 400, "VALIDATION_ERROR")
    conforms(n8n.get("/api/v1/tickets/open?group_key=203.0.113.11", headers=headers), 200)
    conforms(n8n.post("/api/v1/tickets/record", json=body, headers=headers), 201)
    conforms(n8n.post("/api/v1/tickets/record", json={**body, "title": "changed"}, headers=headers),
             409, "IDEMPOTENCY_CONFLICT")
    conforms(n8n.get("/nothing-here"), 404, "NOT_FOUND")

    too_big = n8n.post("/api/v1/tickets/record", data="x" * (65 * 1024), content_type="application/json",
                       headers={**headers, "Idempotency-Key": "exec-2-applied"})
    conforms(too_big, 413, "VALIDATION_ERROR")

    def broken(*_args, **_kwargs):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(core, "record", broken)
    failure = n8n.post("/api/v1/tickets/record", json=body, headers={**headers, "Idempotency-Key": "exec-3-applied"})
    conforms(failure, 500, "SERVER_ERROR")
    assert "disk gone" not in failure.get_data(as_text=True)
