"""Read-only operator comparison + terminal journal CAS, with no business redispatch."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib

import pytest

from tests.test_shared_control_api import control, intent, send
from tools.control_audit import ControlAudit


def uncertain(control, monkeypatch, *, dispatch=True):
    client, engine, audit, items = control
    original = engine.withdraw
    calls = []

    def lose_ack(*args):
        calls.append(1)
        if dispatch:
            original(*args)
        raise RuntimeError("synthetic ACK lost")

    monkeypatch.setattr(engine, "withdraw", lose_ack)
    assert send(client, payload=intent()).status_code == 500
    status = send(client, "/candidate/v1/shared/requests/status", method="GET").get_json()["result"]
    return status["journal_id"], calls


def review(client, journal_id, seat="op"):
    return send(client, "/candidate/v1/shared/journals/" + journal_id, seat=seat, method="GET")


def resolution_body(snapshot):
    return {"executor_stopped": True, "evidence_ref": "synthetic/operator-journal-review",
            "expected_revision": snapshot["revision"], "review_hash": snapshot["review_hash"]}


def resolve(client, journal_id, payload, key="resolve-request-1", seat="op"):
    return send(client, f"/candidate/v1/shared/journals/{journal_id}/resolve", payload, seat=seat, key=key)


def test_terminal_business_can_resolve_ack_journal_without_redispatch(control, monkeypatch):
    client, engine, audit, items = control
    journal_id, calls = uncertain(control, monkeypatch)
    assert review(client, journal_id, seat="A").status_code == 403
    snapshot = review(client, journal_id).get_json()["result"]
    assert snapshot["resolution_allowed"] is True and snapshot["related_state"] == "done"
    assert "context" not in snapshot and "synthetic-applied-D" not in str(snapshot)
    assert resolve(client, journal_id, resolution_body(snapshot), seat="A").status_code == 403
    answer = resolve(client, journal_id, resolution_body(snapshot))
    assert answer.get_json()["result"]["state"] == "journal_resolved"
    assert resolve(client, journal_id, resolution_body(snapshot)).get_json() == answer.get_json()
    assert send(client, payload=intent()).get_json()["error"]["code"] == "OPERATOR_RESOLVED"
    assert len(calls) == 1 and engine.target.active(intent()["resource"])
    assert all(t["status"] == "verified" for t in items.values())
    with closing(audit.connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM resolutions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM events WHERE endpoint='operator_journal_resolution'").fetchone()[0] == 1


def test_no_dispatch_evidence_stays_held(control, monkeypatch):
    client, engine, audit, items = control
    journal_id, calls = uncertain(control, monkeypatch, dispatch=False)
    snapshot = review(client, journal_id).get_json()["result"]
    assert snapshot["related_state"] == "not_seen" and snapshot["resolution_allowed"] is False
    assert resolve(client, journal_id, resolution_body(snapshot)).status_code == 409
    assert audit.journal(journal_id)["state"] == "pending" and len(calls) == 1


def test_pending_business_requires_repair_and_old_review_hash_is_stale(control, monkeypatch):
    client, engine, audit, items = control
    assert send(client, payload=intent(), key="owner-a-withdraw").status_code == 200
    original = engine.withdraw

    def interrupted(*args):
        original(*args, fault="after_target")
        raise RuntimeError("synthetic ACK lost")

    monkeypatch.setattr(engine, "withdraw", interrupted)
    assert send(client, payload=intent("D"), seat="D", key="owner-d-withdraw").status_code == 500
    journal_id = send(client, "/candidate/v1/shared/requests/status", seat="D", key="owner-d-withdraw", method="GET").get_json()["result"]["journal_id"]
    old = review(client, journal_id).get_json()["result"]
    assert old["resolution_allowed"] is False and old["related_state"] == "pending"
    assert resolve(client, journal_id, resolution_body(old)).status_code == 409
    repaired = send(client, f"/candidate/v1/shared/plans/{old['plan_id']}/repair",
        {"executor_stopped": True, "evidence_ref": "synthetic/repair-before-journal-close"}, seat="op", key="operator-repair-1")
    assert repaired.get_json()["result"]["state"] == "reconciled"
    assert resolve(client, journal_id, resolution_body(old)).get_json()["error"]["code"] == "STALE_REVIEW"
    fresh = review(client, journal_id).get_json()["result"]
    assert fresh["resolution_allowed"] is True
    assert resolve(client, journal_id, resolution_body(fresh)).status_code == 200
    with closing(engine.target.connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 2


def test_late_api_ack_changes_revision_and_prevents_stale_resolution(control, monkeypatch):
    client, engine, audit, items = control
    journal_id, _ = uncertain(control, monkeypatch)
    old = review(client, journal_id).get_json()["result"]
    data = {"ok": True, "synthetic_only": True, "allow_target_call": False,
            "result": {"state": "withdrawn_waiting", "plan_id": None}}
    audit.finish("owner-A", hashlib.sha256(b"request-0001").hexdigest(), 200, data)
    assert resolve(client, journal_id, resolution_body(old)).get_json()["error"]["code"] == "STALE_REVIEW"
    assert audit.journal(journal_id)["state"] == "done"


def test_resolution_atomic_audit_failure_rolls_back_and_can_retry(control, monkeypatch):
    client, engine, audit, items = control
    journal_id, _ = uncertain(control, monkeypatch)
    snapshot = review(client, journal_id).get_json()["result"]
    with closing(audit.connect()) as conn:
        conn.execute("CREATE TRIGGER fail_resolution BEFORE INSERT ON events WHEN NEW.endpoint='operator_journal_resolution' "
                     "BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    assert resolve(client, journal_id, resolution_body(snapshot)).status_code == 500
    assert audit.journal(journal_id)["state"] == "pending" and audit.journal(journal_id)["revision"] == 0
    with closing(audit.connect()) as conn:
        conn.execute("DROP TRIGGER fail_resolution")
    assert resolve(client, journal_id, resolution_body(snapshot)).status_code == 200


def test_concurrent_resolutions_and_reused_operator_key_are_checked(control, monkeypatch):
    client, engine, audit, items = control
    journal_id, calls = uncertain(control, monkeypatch)
    snapshot = review(client, journal_id).get_json()["result"]
    payload = resolution_body(snapshot)
    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(lambda n: resolve(client.application.test_client(), journal_id, payload, key=f"operator-resolve-{n}").status_code, range(2)))
    assert sorted(answers) == [200, 409] and len(calls) == 1
    with closing(audit.connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM resolutions").fetchone()[0] == 1
        key_hash = conn.execute("SELECT key_hash FROM resolutions").fetchone()[0]
    assert audit.begin("operator", key_hash, "different-fingerprint")[0] == "conflict"


def test_existing_operator_mutation_key_cannot_be_reused_for_resolution(control, monkeypatch):
    client, engine, audit, items = control
    journal_id, _ = uncertain(control, monkeypatch)
    snapshot = review(client, journal_id).get_json()["result"]
    audit.begin("operator", hashlib.sha256(b"resolve-request-1").hexdigest(), "another-operation")
    assert resolve(client, journal_id, resolution_body(snapshot)).get_json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_audit_v1_requires_migration_and_done_state_cannot_be_overwritten(control, monkeypatch):
    client, engine, audit, items = control
    journal_id, _ = uncertain(control, monkeypatch)
    snapshot = review(client, journal_id).get_json()["result"]
    resolve(client, journal_id, resolution_body(snapshot))
    with pytest.raises(RuntimeError):
        audit.finish("owner-A", hashlib.sha256(b"request-0001").hexdigest(), 200, {})
    with closing(audit.connect()) as conn:
        conn.execute("PRAGMA user_version=1")
    with pytest.raises(ValueError):
        ControlAudit(audit.path)
