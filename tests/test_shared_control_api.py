"""Reference API protocol with an explicit in-memory C test double, not school C."""
from copy import deepcopy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, request
from jsonschema import Draft202012Validator
import pytest

from tools.control_audit import ControlAudit
from tools.resource_gate import ResourceGate
from tools.shared_claims import ClaimBook
from tools.shared_control_api import Principal, create_shared_control_api
from tools.shared_release_simulation import SharedReleaseSimulation
from tools.simulated_execution import CTestClient, SimulatedTarget

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts/candidate-shared-control.schema.json").read_text(encoding="utf-8"))
R = {"asset_id": "synthetic-portal", "via": "portal", "action": "block", "target": "203.0.113.11"}
TOKENS = {"A": "synthetic-control-owner-a", "D": "synthetic-control-owner-d",
          "B": "synthetic-control-owner-b", "op": "synthetic-control-recovery"}


def intent(seat="A", operation="withdraw"):
    return {"operation": operation, "resource": deepcopy(R), "ticket_id": f"T-20261024-{1 if seat == 'A' else 2:04d}",
            "action_id": "synthetic-applied-" + seat}


@pytest.fixture
def control(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js required for actual guard JS in the synthetic fixture")
    backend = Flask("memory-C-test-double")
    items, cache = {}, {}
    for index, seat in enumerate(("A", "D"), 1):
        ticket_id = f"T-20261024-{index:04d}"
        items[ticket_id] = {"ticket_id": ticket_id, "seat": seat, "asset_id": R["asset_id"], "case_id": "S1" if seat == "A" else "S12",
            "group_key": "synthetic-user" if seat == "A" else R["target"], "title": "synthetic", "event_ids": ["synthetic-" + seat],
            "status": "verified", "active": True, "actions": [{"action_id": "synthetic-applied-" + seat,
                "duplicate": False, "bot": "112", "via": "portal", "action": "block", "target": R["target"], "result": "applied"}]}

    @backend.get("/api/v1/tickets/active")
    def active():
        return jsonify(ok=True, resource=R, tickets=[{"seat": t["seat"], "ticket_id": t["ticket_id"], "status": t["status"],
            "active_actions": [{"bot": "112", **{k: R[k] for k in ("via", "action", "target")}}]} for t in items.values() if t["active"]])

    @backend.get("/api/v1/tickets/<ticket_id>")
    def detail(ticket_id):
        return jsonify(ok=True, ticket=items[ticket_id]) if ticket_id in items else (jsonify(ok=False), 404)

    @backend.post("/api/v1/tickets/record")
    def record():
        body, key = request.get_json(), request.headers["Idempotency-Key"]
        wire = json.dumps(body, sort_keys=True)
        if key in cache:
            assert cache[key][0] == wire
            return jsonify(cache[key][1])
        ticket = next(t for t in items.values() if t["seat"] == body["seat"])
        ticket["actions"].append({**body["action"], "action_id": key, "duplicate": False})
        ticket.update(active=False, status="restored")
        ack = {"ok": True, "ticket_id": ticket["ticket_id"], "status": "restored", "created": False, "duplicate": False}
        cache[key] = wire, ack
        return jsonify(ack)

    target = SimulatedTarget(tmp_path / "target.db", create=True)
    target.perform("synthetic-initial-block", R, "apply")
    engine = SharedReleaseSimulation(ResourceGate(tmp_path / "gate.db", create=True), ClaimBook(tmp_path / "claims.db", create=True),
        target, CTestClient(backend.test_client(), backend.test_client(), "synthetic-C-key-0001"))
    audit = ControlAudit(tmp_path / "audit.db", create=True)
    credentials = {TOKENS[s]: Principal("owner-" + s, "owner", frozenset({s})) for s in ("A", "B", "D")}
    credentials[TOKENS["op"]] = Principal("operator", "recovery", frozenset())
    app = create_shared_control_api(engine, audit, credentials)
    return app.test_client(), engine, audit, items


def send(client, path="/candidate/v1/shared/intents", payload=None, seat="A", key="request-0001", method="POST", **kwargs):
    headers = {"X-Control-Key": TOKENS.get(seat, seat), "Idempotency-Key": key}
    response = client.open(path, method=method, json=payload, headers=headers, **kwargs)
    Draft202012Validator(SCHEMA).validate(response.get_json())
    assert response.get_json()["allow_target_call"] is False
    return response


def prepared(engine, fault):
    a, d = intent("A"), intent("D")
    assert engine.withdraw("seed-withdraw-a", R, a["ticket_id"], a["action_id"])["state"] == "withdrawn_waiting"
    return engine.withdraw("seed-withdraw-d", R, d["ticket_id"], d["action_id"], fault=fault)["plan_id"]


def test_owner_auth_and_server_seat_scope(control):
    client, engine, audit, items = control
    assert send(client, payload=intent(), seat="wrong-key-00000000").status_code == 401
    assert send(client, payload=intent("D"), seat="A").status_code == 403
    assert send(client, payload={**intent(), "seat": "D"}).status_code == 400
    assert send(client, payload=intent(), seat="op").status_code == 403
    assert send(client, payload=intent()).get_json()["result"]["state"] == "withdrawn_waiting"
    assert engine.target.active(R) and items[intent()["ticket_id"]]["status"] == "verified"


def test_actor_scoped_idempotency_and_body_conflict(control):
    client, engine, audit, items = control
    first = send(client, payload=intent(), key="same-key-0001")
    assert send(client, payload=intent(), key="same-key-0001").get_json() == first.get_json()
    assert send(client, payload=intent(operation="retain"), key="same-key-0001").status_code == 409
    final = send(client, payload=intent("D"), seat="D", key="same-key-0001")
    assert final.get_json()["result"]["state"] == "released" and not engine.target.active(R)
    assert send(client, payload=intent("D"), seat="D", key="same-key-0001").get_json() == final.get_json()


def test_plan_read_redacts_other_claim_payloads(control):
    client, engine, audit, items = control
    plan_id = prepared(engine, "before_target")
    path = "/candidate/v1/shared/plans/" + plan_id
    data = send(client, path, seat="A", method="GET").get_json()["result"]
    assert data["state"] == "prepared" and data["claims_count"] == 2
    assert "claims" not in data and "synthetic-applied-D" not in json.dumps(data)
    assert send(client, path, seat="B", method="GET").status_code == 403


def test_recovery_role_cancel_before_effect_restores_logical_owners(control):
    client, engine, audit, items = control
    plan_id = prepared(engine, "before_target")
    path = f"/candidate/v1/shared/plans/{plan_id}/cancel"
    payload = {"executor_stopped": True, "evidence_ref": "synthetic/operator-check"}
    assert send(client, path, payload, seat="A").status_code == 403
    assert send(client, path, {**payload, "executor_stopped": False}, seat="op").status_code == 400
    response = send(client, path, payload, seat="op")
    assert response.get_json()["result"]["state"] == "cancelled"
    assert engine.target.receipt(plan_id) is None and engine.target.active(R)
    assert all(t["status"] == "verified" for t in items.values())
    assert engine.gate.inspect("seed-withdraw-d")["state"] == "done"
    assert send(client, path, payload, seat="op").get_json() == response.get_json()
    # Cancelled intents remain consumed. A fresh intent is needed to withdraw again.
    assert send(client, payload=intent(), key="fresh-withdraw-a").get_json()["result"]["state"] == "withdrawn_waiting"


@pytest.mark.parametrize("fault", ["after_target", "after_first_record", "after_book_complete"])
def test_cancel_after_effect_denied_but_record_only_repair_allowed(control, fault):
    client, engine, audit, items = control
    plan_id = prepared(engine, fault)
    payload = {"executor_stopped": True, "evidence_ref": "synthetic/recovery-check"}
    root = f"/candidate/v1/shared/plans/{plan_id}"
    assert send(client, root + "/cancel", payload, seat="op", key="cancel-0001").status_code == 409
    response = send(client, root + "/repair", payload, seat="op", key="repair-0001")
    assert response.get_json()["result"]["state"] == "reconciled"
    assert not engine.target.active(R) and all(t["status"] == "restored" for t in items.values())
    with closing(engine.target.connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 2


def test_inflight_api_journal_never_reexecutes_unknown_result(control, monkeypatch):
    client, engine, audit, items = control
    original = engine.withdraw
    calls = []

    def lose_ack(*args):
        calls.append(1)
        original(*args)
        raise RuntimeError("synthetic-sensitive-exception")

    monkeypatch.setattr(engine, "withdraw", lose_ack)
    assert send(client, payload=intent()).status_code == 500
    response = send(client, payload=intent())
    assert response.status_code == 409 and response.get_json()["error"]["code"] == "RECONCILIATION_REQUIRED"
    assert len(calls) == 1 and "sensitive" not in str(response.get_json())
    state = send(client, "/candidate/v1/shared/requests/status", method="GET").get_json()["result"]["state"]
    assert state == "journal_pending"


@pytest.mark.parametrize("raw", [b'{', b'{"operation":"withdraw","operation":"retain"}', b'{"x":NaN}', b'\xff'])
def test_malformed_json_is_not_accepted(control, raw):
    client, engine, audit, items = control
    response = client.post("/candidate/v1/shared/intents", data=raw, content_type="application/json",
                           headers={"X-Control-Key": TOKENS["A"], "Idempotency-Key": "request-0001"})
    assert response.status_code == 400
    Draft202012Validator(SCHEMA).validate(response.get_json())


def test_audit_is_redacted_and_unavailable_audit_fails_closed(control, monkeypatch):
    client, engine, audit, items = control
    send(client, payload=intent())
    for path in audit.path.parent.iterdir():
        if path.is_file():
            assert all(token.encode() not in path.read_bytes() for token in TOKENS.values())
    with closing(audit.connect()) as conn:
        event = conn.execute("SELECT principal,endpoint,status FROM events").fetchone()
        assert tuple(event) == ("owner-A", "intent", 200)

    def unavailable(*args):
        raise sqlite3.OperationalError("synthetic database failure")

    monkeypatch.setattr(audit, "begin", unavailable)
    assert send(client, payload=intent("D"), seat="D").status_code == 500
    assert engine.target.active(R)


def test_not_found_and_oversized_requests_use_contract_errors(control):
    client, engine, audit, items = control
    assert send(client, "/candidate/v1/shared/plans/shared-" + "0" * 32, method="GET").status_code == 404
    response = client.post("/candidate/v1/shared/intents", data=b'x' * 9000, content_type="application/json",
                           headers={"X-Control-Key": TOKENS["A"]})
    assert response.status_code == 413
    Draft202012Validator(SCHEMA).validate(response.get_json())


def test_concurrent_same_actor_key_does_not_dispatch_twice(control, monkeypatch):
    client, engine, audit, items = control
    started, proceed = threading.Event(), threading.Event()
    original = engine.withdraw
    calls = []

    def delayed(*args):
        calls.append(1)
        started.set()
        assert proceed.wait(5)
        return original(*args)

    monkeypatch.setattr(engine, "withdraw", delayed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(lambda: send(client.application.test_client(), payload=intent()).status_code)
        try:
            assert started.wait(5)
            assert send(client.application.test_client(), payload=intent()).status_code == 409
        finally:
            proceed.set()
        assert first.result(timeout=10) == 200
    assert len(calls) == 1


def test_audit_event_failure_does_not_ack_success_or_redispatch(control, monkeypatch):
    client, engine, audit, items = control
    original = audit.event

    def fail(*args):
        raise sqlite3.OperationalError("synthetic audit unavailable")

    monkeypatch.setattr(audit, "event", fail)
    assert send(client, payload=intent()).status_code == 500
    monkeypatch.setattr(audit, "event", original)
    assert send(client, payload=intent()).status_code == 200
    with closing(engine.book.connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM intents").fetchone()[0] == 1


def test_conflicting_server_principal_grants_are_rejected(control):
    client, engine, audit, items = control
    with pytest.raises(ValueError):
        create_shared_control_api(engine, audit, {
            "synthetic-config-key-1": Principal("same", "owner", frozenset({"A"})),
            "synthetic-config-key-2": Principal("same", "owner", frozenset({"D"}))})
