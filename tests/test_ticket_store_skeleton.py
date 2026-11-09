"""Ticket store skeleton: storage, samples, read API and port split (no n8n logic yet)."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest
from referencing import Registry, Resource

from ticket_store import db, samples
from ticket_store.app import create_dashboard_app, create_n8n_app

ROOT = Path(__file__).resolve().parents[1]
KEY = "test-key-not-a-secret-0001"


def ticket_validator():
    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "contracts").glob("ticket*.schema.json")]
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)
    schema = json.loads((ROOT / "contracts/ticket.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker(formats=["date-time", "ipv4", "ipv6"]))


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "tickets.db")
    conn = db.connect(path)
    samples.load_samples(conn)
    conn.close()
    return path


def test_samples_follow_ticket_contract_and_cover_every_status():
    tickets = samples.sample_tickets()
    for ticket in tickets:
        ticket_validator().validate(ticket)
        assert ticket["data_origin"] == "sample"
    assert {t["status"] for t in tickets} == set(db.STATUSES)
    assert any(a["result"] == "failed" for t in tickets for a in t["actions"])


def test_stored_ticket_reads_back_as_the_same_contract_ticket(db_path):
    conn = db.connect(db_path)
    for ticket in samples.sample_tickets():
        assert db.get_ticket(conn, ticket["ticket_id"]) == ticket
    assert samples.load_samples(conn) == 0
    with pytest.raises(db.NotFound):
        db.get_ticket(conn, "T-20261024-0000")


def test_one_open_ticket_per_seat_and_group_key(db_path):
    conn = db.connect(db_path)
    open_ticket = next(t for t in samples.sample_tickets() if t["status"] == "open")
    with pytest.raises(Exception):
        db.insert_ticket(conn, {**open_ticket, "ticket_id": "T-20261024-9999", "actions": []})


def test_close_only_verified_or_restored(db_path):
    conn = db.connect(db_path)
    with pytest.raises(db.InvalidTransition):
        db.close_ticket(conn, "T-20261024-9002", "not yet")
    with pytest.raises(db.InvalidTransition, match="active action remains"):
        db.close_ticket(conn, "T-20261024-9001", "block not released")
    closed = db.close_ticket(conn, "T-20261024-9004", "확인 끝", now="2026-10-24T17:00:00+09:00")
    assert closed["status"] == "closed" and closed["closed_at"] == "2026-10-24T17:00:00+09:00"
    ticket_validator().validate(closed)


def test_dashboard_read_api_hides_samples_by_default(db_path):
    client = create_dashboard_app(db_path).test_client()
    body = client.get("/api/v1/tickets").get_json()
    assert body == {"ok": True, "count": 0, "items": [], "counts": dict.fromkeys(db.STATUSES, 0), "last_record_at": None}
    body = client.get("/api/v1/tickets?sample=1&status=verified,restored").get_json()
    assert {i["ticket_id"] for i in body["items"]} == {"T-20261024-9001", "T-20261024-9004"}
    s7 = next(i for i in body["items"] if i["ticket_id"] == "T-20261024-9001")
    assert (s7["mttd_seconds"], s7["mttr_seconds"]) == (8, 42)
    assert client.get("/api/v1/tickets?status=contained").status_code == 400
    detail = client.get("/api/v1/tickets/T-20261024-9006").get_json()
    assert detail["ok"] and [a["result"] for a in detail["ticket"]["actions"]] == ["applied", "failed"]
    missing = client.get("/api/v1/tickets/T-20261024-0000")
    assert missing.status_code == 404 and missing.get_json()["error"]["code"] == "NOT_FOUND"


def test_ports_serve_separate_paths_and_n8n_app_needs_a_key(db_path):
    n8n = create_n8n_app(db_path, KEY).test_client()
    assert n8n.get("/api/v1/tickets").status_code == 404
    assert n8n.get("/").status_code == 404
    with pytest.raises(ValueError):
        create_n8n_app(db_path, "")
    with pytest.raises(ValueError):
        create_n8n_app(db_path, "short")
